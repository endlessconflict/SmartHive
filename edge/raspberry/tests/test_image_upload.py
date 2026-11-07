import email.parser
import email.policy
import io
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pi_node.image_upload import ImageUploader, read_token
from pi_node.outbox import Outbox

NOW = datetime(2026, 10, 6, 14, 3, 21, tzinfo=UTC)


class Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_: object) -> None:
        pass


class Server:
    """Answers each upload with the next status of the script; an exception is raised as is."""

    def __init__(self, *script: int | Exception) -> None:
        self.script = list(script)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request) -> Response:
        self.requests.append(req)
        answer = self.script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if answer >= 400:
            raise urllib.error.HTTPError(req.full_url, answer, "", {}, io.BytesIO(b'{"title": "Image too large"}'))  # type: ignore[arg-type]
        return Response(answer)


@pytest.fixture
def outbox(tmp_path: Path):
    box = Outbox(tmp_path / "outbox.db")
    yield box
    box.close()


def queue(outbox: Outbox, tmp_path: Path, image_id: str, reason: str = "threat") -> bytes:
    data = b"\xff\xd8\xff\xe0" + image_id.encode()
    path = tmp_path / f"{image_id}.jpg"
    path.write_bytes(data)
    meta = json.dumps({"image_id": image_id, "reason": reason}).encode()
    outbox.add_image(image_id, path, "sha", len(data), NOW, reason, meta)
    return data


def uploader(outbox: Outbox, server: Server, now: list[float] | None = None) -> ImageUploader:
    clock = (lambda: now[0]) if now is not None else (lambda: 0.0)
    return ImageUploader("https://gateway.local/", "tok", outbox, clock=clock, opener=server)


def test_an_upload_is_the_multipart_form_the_endpoint_expects(outbox: Outbox, tmp_path: Path) -> None:
    data = queue(outbox, tmp_path, "img-1")
    server = Server(201)
    assert uploader(outbox, server).drain(threading.Event(), float("inf")) == 1
    [req] = server.requests
    assert req.full_url == "https://gateway.local/device/v1/images"
    assert req.get_header("Authorization") == "Bearer tok"
    head = f"Content-Type: {req.get_header('Content-type')}\r\n\r\n".encode()
    form = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(head + req.data)  # type: ignore[operator]
    meta, file = form.iter_parts()
    assert meta.get_param("name", header="content-disposition") == "meta"
    assert json.loads(meta.get_content()) == {"image_id": "img-1", "reason": "threat"}
    assert file.get_content_type() == "image/jpeg" and file.get_content() == data
    assert outbox.pending_images() == []


def test_a_200_means_the_server_already_had_it(outbox: Outbox, tmp_path: Path) -> None:
    queue(outbox, tmp_path, "img-1")
    assert uploader(outbox, Server(200)).drain(threading.Event(), float("inf")) == 1
    assert outbox.pending_images() == []


def test_threat_pictures_go_up_before_the_random_sample(outbox: Outbox, tmp_path: Path) -> None:
    queue(outbox, tmp_path, "sample-1", "sample")
    queue(outbox, tmp_path, "varroa-1", "varroa")
    queue(outbox, tmp_path, "threat-1", "threat")
    server = Server(201, 201, 201)
    uploader(outbox, server).drain(threading.Event(), float("inf"))
    assert [json.loads(r.data.split(b"\r\n\r\n")[1].split(b"\r\n")[0])["image_id"]  # type: ignore[union-attr]
            for r in server.requests] == ["threat-1", "varroa-1", "sample-1"]


@pytest.mark.parametrize("status", [409, 413, 415, 422])
def test_a_rejected_image_is_not_retried(outbox: Outbox, tmp_path: Path, status: int) -> None:
    queue(outbox, tmp_path, "bad")
    queue(outbox, tmp_path, "good")
    server = Server(status, 201)
    assert uploader(outbox, server).drain(threading.Event(), float("inf")) == 1
    assert outbox.pending_images() == []
    assert outbox._db.execute("SELECT rejected FROM images WHERE image_id = 'bad'").fetchone() == (
        f"{status} Image too large",)
    assert (tmp_path / "bad.jpg").exists()  # kept for a look until the purge


@pytest.mark.parametrize("failure", [500, 503, 401, urllib.error.URLError("refused"), TimeoutError()])
def test_a_failure_backs_off_and_retries(outbox: Outbox, tmp_path: Path, failure: int | Exception) -> None:
    queue(outbox, tmp_path, "img-1")
    now = [0.0]
    server = Server(failure, 201)
    up = uploader(outbox, server, now)
    assert up.drain(threading.Event(), float("inf")) == 0
    assert outbox._db.execute("SELECT attempts FROM images").fetchone() == (1,)
    assert up.drain(threading.Event(), float("inf")) == 0  # still backing off: no request
    assert len(server.requests) == 1
    now[0] = 1.0
    assert up.drain(threading.Event(), float("inf")) == 1


def test_a_missing_file_is_rejected_not_retried(outbox: Outbox, tmp_path: Path) -> None:
    queue(outbox, tmp_path, "img-1")
    (tmp_path / "img-1.jpg").unlink()
    assert uploader(outbox, Server()).drain(threading.Event(), float("inf")) == 0
    assert outbox.pending_images() == []


def test_an_empty_token_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "token").write_text("\n")
    with pytest.raises(ValueError, match="device token"):
        read_token(tmp_path / "token")
