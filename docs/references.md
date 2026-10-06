# References

Status: Living document. Add an entry when a doc cites something new.

Datasets marked "verify license" must be checked on their own page and recorded in the asset manifest before use.

## Synthetic data and small object detection

- Dwibedi, D., Misra, I., Hebert, M. (2017). *Cut, Paste and Learn: Surprisingly Easy Synthesis for Instance Detection.* ICCV. [arXiv:1708.01642](https://arxiv.org/abs/1708.01642)
- Ghiasi, G. et al. (2021). *Simple Copy-Paste Is a Strong Data Augmentation Method for Instance Segmentation.* CVPR. [CVF open access](https://openaccess.thecvf.com/content/CVPR2021/html/Ghiasi_Simple_Copy-Paste_Is_a_Strong_Data_Augmentation_Method_for_Instance_CVPR_2021_paper.html)
- Akyon, F. C., Altinuc, S. O., Temizel, A. (2022). *Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection.* [arXiv:2202.06934](https://arxiv.org/abs/2202.06934), code: [obss/sahi](https://github.com/obss/sahi)
- Denninger, M. et al. *BlenderProc.* DLR-RM. [GitHub](https://github.com/DLR-RM/BlenderProc) (GPL-3.0)
- *Generate-Paste-Blend-Detect* (diffusion-generated objects pasted onto backgrounds for whitefly detection with YOLOv8), cited in the synthetic data search results; full citation to be added when the paper is read.

## Varroa, hornets and bee vision

- Bilík, Š. et al. (2021). *Visual Diagnosis of the Varroa Destructor Parasitic Mite in Honeybees Using Object Detector Techniques.* Sensors. [arXiv:2103.03133](https://arxiv.org/abs/2103.03133)
- Bjerge, K. et al. (2019). *A computer vision system to monitor the infestation level of Varroa destructor in a honeybee colony.* Computers and Electronics in Agriculture 164.
- O'Shea-Wheller, T. A., Corbett, A., Osborne, J. L., Recker, M., Kennedy, P. J. (2024). *VespAI: a deep learning-based system for the detection of invasive hornets.* Communications Biology 7, 354. [PMC10991484](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10991484/)
- Sittinger, M. et al. *Insect Detect: an open-source DIY camera trap for automated insect monitoring.* [GitHub](https://github.com/maxsitt/insect-detect)
- Survey: *Machine Learning and Computer Vision Techniques in Continuous Beehive Monitoring Applications.* [arXiv:2208.00085](https://arxiv.org/pdf/2208.00085)

## Image datasets

| Dataset | Link | License |
|---|---|---|
| VarroaDataset (TU Wien) | [Zenodo 4085044](https://zenodo.org/record/4085044) | Verify |
| Varroa mites on sticky boards | [Zenodo 10231845](https://zenodo.org/records/10231845) | Verify |
| Insect Detect training images | [Zenodo 7725941](https://zenodo.org/records/7725941) | Verify |
| BEEHIVE (in-hive images) | [Mendeley 5yz78xxpmy](https://data.mendeley.com/datasets/5yz78xxpmy) | CC BY-NC |
| TFDS `bee_dataset` | TensorFlow Datasets catalog | GPL (per catalog) |
| Kaggle BeeImage / Honey Bee Annotated Images | Kaggle | Verify |
| BuzzSet v1.0 (pollinators in the field) | [arXiv:2508.19762](https://arxiv.org/pdf/2508.19762) | Verify |

## Hive biology and telemetry

- Meikle, W. G. et al. (2018). *Using within-day hive weight changes to measure environmental effects on honey bee colonies.* PLoS ONE. [PMC5965838](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5965838/)
- *Modelling daily weight variation in honey bee hives.* [arXiv:2211.02335](https://arxiv.org/pdf/2211.02335)
- Becher, M. A. et al. (2014). *BEEHAVE: a systems model of honeybee colony dynamics and foraging to explore multifactorial causes of colony failure.* Journal of Applied Ecology. [PMC4283046](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4283046/)
- Brood nest thermoregulation at 34 to 36 °C and brood humidity around 50 to 60 %: see for example [PMC2813292](https://pmc.ncbi.nlm.nih.gov/articles/PMC2813292/) and [PMC8079341](https://pmc.ncbi.nlm.nih.gov/articles/PMC8079341)
- *Anomaly Detection in Beehives: An Algorithm Comparison.* [arXiv:2110.03945](https://arxiv.org/pdf/2110.03945)
- MSPB: *a longitudinal multi-sensor dataset with phenotypic trait measurements from honey bees.* Scientific Data (2024). [arXiv:2311.10876](https://arxiv.org/abs/2311.10876), data [Zenodo 8371700](https://zenodo.org/records/8371700), code [MuSAELab/MSPB](https://github.com/MuSAELab/MSPB)
- UrBAN: *Urban Beehive Acoustics and PheNotyping Dataset.* [arXiv:2406.03657](https://arxiv.org/abs/2406.03657)
- Nolasco, I., Benetos, E. (2018). *To bee or not to bee: investigating machine learning approaches for beehive sound recognition.* Dataset [Zenodo 1321278](https://zenodo.org/record/1321278)

## Weather

- Open-Meteo: open-source weather API (AGPL-3.0 server, CC BY 4.0 data), historical reanalysis back to 1940. [open-meteo.com](https://open-meteo.com/)

## Hardware and edge inference

- Raspberry Pi 3B power measurements (1.4 W idle, 3.7 W full CPU load, headless): [Pi Dramble](https://pidramble.com/node/27)
- Ultralytics guide to YOLO on Raspberry Pi (NCNN recommended on ARM): [docs.ultralytics.com/guides/raspberry-pi](https://docs.ultralytics.com/guides/raspberry-pi)
- LearnOpenCV, *YOLO11 on Raspberry Pi*: [learnopencv.com/yolo11-on-raspberry-pi](https://learnopencv.com/yolo11-on-raspberry-pi/)
- TFLite SSD MobileNet at about 1 fps on a Pi 3 and about 5 fps on a Pi 4: [DigiKey Maker.io guide](https://www.digikey.com/es/maker/projects/how-to-perform-object-detection-with-tensorflow-lite-on-raspberry-pi/b929e1519c7c43d5b2c6f89984883588), [AlertTrap, arXiv:2112.13341](https://arxiv.org/pdf/2112.13341)
- NanoDet-Plus (Apache-2.0): [RangiLyu/nanodet](https://github.com/RangiLyu/nanodet)
- Linux kernel DHT11 IIO driver and `dtoverlay=dht11`: [wiki.kewl.org/interfaces:dht11](https://wiki.kewl.org/interfaces:dht11)

## Licensing notes used in the stack decisions

- Ultralytics license terms (AGPL-3.0 or enterprise): [ultralytics.com/license](https://www.ultralytics.com/license)
- TimescaleDB editions (Apache-2.0 vs Timescale License): [TimescaleDB editions](https://www.tigerdata.com/docs/about/latest/timescaledb-editions)
- MinIO community edition: maintenance mode December 2025, archived February 2026: [itsfoss.com news](https://itsfoss.com/news/minio-moves-away-from-open-source/), [overview of alternatives](https://glukhov.org/data-infrastructure/object-storage/minio-dead/)
- InfluxDB 3 Core license and query file limit: [InfluxData announcement](https://influxdata.com/blog/influxdb3-open-source-public-alpha), [community update](https://community.influxdata.com/t/announcing-influxdb-3-enterprise-free-for-at-home-use-and-an-update-on-influxdb-3-core-s-72-hour-limitation/56109)
- Redis license changes and Valkey (BSD-3): [OpenUK note](https://openuk.uk/wp-content/uploads/2025/05/Redis-reverts-to-open-source.pdf)
- FLUX.1 [schnell] (Apache-2.0, 12B parameters): [Hugging Face model card](https://huggingface.co/black-forest-labs/FLUX.1-schnell)
