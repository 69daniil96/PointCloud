# PointCloud Processing Pipeline

Практичный runbook для запуска проекта на Windows: Conda + Docker Desktop.

## Что это

Проект собирает облака точек из фото в двух режимах:
- Наземная съемка: COLMAP -> PDAL -> Open3D
- Съемка с дрона: ODM (Docker) -> PDAL -> Open3D

## Требования

- Windows 10/11
- Conda (Anaconda или Miniconda)
- Docker Desktop (нужен для режима с дроном/ODM)

Важно для Windows:
- Docker Desktop должен быть запущен (Engine running).
- Не задавайте `DOCKER_HOST=unix:///var/run/docker.sock` в `.env` (это Linux-сокет и он ломает запуск Docker CLI в Windows).

## Установка инструментов и загрузка проекта

### 1. Как скачать проект с GitHub

Вариант A (рекомендуется, через Git):

```bash
git clone https://github.com/69daniil96/PointCloud.git
cd PointCloud
```

Вариант B (без Git):
- Откройте страницу репозитория в браузере: https://github.com/69daniil96/PointCloud
- Нажмите Code -> Download ZIP
- Распакуйте архив, например в `C:\PointCloud`

### 2. Как скачать и установить Anaconda3

- Сайт Anaconda: https://www.anaconda.com/download
- Скачайте Anaconda3 для Windows (64-bit) и установите с настройками по умолчанию.
- После установки откройте Anaconda Prompt и проверьте:

```bash
conda --version
```

### 3. Как скачать и установить Docker Desktop

- Страница загрузки Docker Desktop: https://www.docker.com/products/docker-desktop/
- Скачайте Docker Desktop для Windows и установите.
- Запустите Docker Desktop и дождитесь статуса Engine running.
- Проверьте в терминале:

```bash
docker --version
docker ps
```

### 4. Как скачать контейнер (образ) ODM

После установки Docker Desktop выполните:

```bash
docker pull opendronemap/odm:latest
```

Проверить, что образ скачан:

```bash
docker images | findstr opendronemap/odm
```

### 5. Как запустить контейнер ODM вручную

Из корня проекта `PointCloud` выполните:

```bash
docker run --rm -v "${PWD}\data\output\drone\odm:/datasets" -v "${PWD}\data\input\drone:/datasets/code/images" opendronemap/odm:latest --project-path /datasets code
```

Что делает эта команда:
- монтирует выходную папку в `/datasets`
- монтирует входные фото в `/datasets/code/images`
- запускает ODM на датасете `code`

Результаты будут в папке:
- `data/output/drone/odm/code`

Рекомендуемый вариант для этого проекта:
- запускать ODM через CLI проекта (он сам формирует корректную команду Docker):

```bash
python -m src.ui.cli process-drone data/input/drone --pull-docker-image
```

## Быстрый запуск с нуля

### 1. Создать и активировать окружение

```bash
conda create -n myenv python=3.10.19 -y
conda activate myenv
```

### 2. Установить Python-зависимости

```bash
pip install -r requirements.txt
```

Если каких-то пакетов не хватает, установите через conda-forge:

```bash
conda install -c conda-forge colmap opencv open3d pdal python-laspy -y
```

### 3. Запустить Docker Desktop

Проверьте, что daemon поднят:

```bash
docker --version
docker ps
```

Если `docker ps` не отвечает, откройте Docker Desktop и дождитесь статуса Engine running.

### 4. Подтянуть образ ODM

```bash
docker pull opendronemap/odm:latest
```

### 5. Проверить зависимости проекта

```bash
python -m src.ui.cli check-dependencies
```

Ожидается итоговая строка: `[OK] Все необходимые зависимости установлены!`.

## Подготовка данных

Положите изображения в папки:

- data/input/ground - фото наземной съемки
- data/input/drone - фото с дрона

## Запуск обработки

### Наземная съемка

```bash
python -m src.ui.cli process-ground data/input/ground
```

По умолчанию в конце откроется окно визуализации Open3D.

Чтобы запустить только обработку без окна визуализации:

```bash
python -m src.ui.cli process-ground data/input/ground --no-visualization
```

Выбрать, какие слои показать в визуализации на старте:

```bash
python -m src.ui.cli process-ground data/input/ground --layers final,ground,vegetation
```

Использовать пресет слоев:

```bash
python -m src.ui.cli process-ground data/input/ground --layers-preset terrain
```

### Съемка с дрона

```bash
python -m src.ui.cli process-drone data/input/drone
```

Если это первый запуск на машине и образ ODM еще не загружен, используйте:

```bash
python -m src.ui.cli process-drone data/input/drone --pull-docker-image
```

Чтобы запустить без окна визуализации:

```bash
python -m src.ui.cli process-drone data/input/drone --no-visualization
```

Выбрать слои визуализации на старте:

```bash
python -m src.ui.cli process-drone data/input/drone --layers final,ground,vegetation,outliers
```

Использовать пресет слоев:

```bash
python -m src.ui.cli process-drone data/input/drone --layers-preset quality-control
```

Пресеты слоев:
- `terrain`: `final,ground`
- `vegetation`: `final,vegetation,ground`
- `quality-control`: `final,outliers,no_ground,no_outliers`
- `all`: `final,ground,vegetation,outliers,no_ground,no_outliers`

Приоритет опций:
- Если передан `--layers`, он переопределяет `--layers-preset`.
- Если `--layers` не передан, используются слои из `--layers-preset`.

Доступные имена слоев:
- `final`
- `ground`
- `vegetation`
- `outliers`
- `no_ground`
- `no_outliers`

В окне Open3D можно переключать видимость слоев клавишами `1..9`.

## Полезные команды

```bash
python -m src.ui.cli show-config
python -m src.ui.cli list-tools
python -m src.ui.cli process-ground --help
python -m src.ui.cli process-drone --help
```

## Где смотреть результат

- Результаты наземной съемки: `data/output/ground`
- COLMAP (исходная реконструкция): `data/output/ground/colmap/reconstruction.ply`
- PDAL (промежуточные облака): `data/output/ground/pdal/*.las`
- Явные слои после PDAL: `*_ground.las`, `*_vegetation.las`, `*_outliers.las`, `*_no_ground.las`, `*_no_outliers.las`
- Финальный файл после Open3D: `data/output/ground/open3d/*_processed.ply`
- Результаты дронной съемки: `data/output/drone`
- ODM-результаты: `data/output/drone/odm/...`
- PDAL (промежуточные облака): `data/output/drone/pdal/*.las`
- Явные слои после PDAL: `*_ground.las`, `*_vegetation.las`, `*_outliers.las`, `*_no_ground.las`, `*_no_outliers.las`
- Финальный файл после Open3D: `data/output/drone/open3d/*_processed.ply`
- Временные файлы: `data/temp`
- Логи: `data/logs`

## Запуск финального PLY отдельно

### Открыть последний финальный PLY автоматически

```bash
python -c "import glob,open3d as o3d; p=sorted(glob.glob('data/output/ground/open3d/*_processed.ply'))[-1]; pc=o3d.io.read_point_cloud(p); print('Открываю:', p); o3d.visualization.draw_geometries([pc], window_name='Final PLY')"
```

### Открыть конкретный PLY по пути

```bash
python -c "import open3d as o3d; p=r'data/output/ground/open3d/reconstruction_no_outliers_no_ground_downsampled_processed.ply'; pc=o3d.io.read_point_cloud(p); o3d.visualization.draw_geometries([pc], window_name='Final PLY')"
```

### Открыть последний финальный PLY для дрона

```bash
python -c "import glob,open3d as o3d; files=sorted(glob.glob('data/output/drone/open3d/*_processed.ply')); print('Найдено:', len(files)); p=files[-1]; pc=o3d.io.read_point_cloud(p); print('Открываю:', p); o3d.visualization.draw_geometries([pc], window_name='Drone Final PLY')"
```

Примечание:
- Шаблон должен быть `*_processed.ply`.
- Если указать `_processed.ply` без `*`, будет ошибка `IndexError: list index out of range`.

## Частые проблемы

### COLMAP не найден

```bash
conda install -c conda-forge colmap -y
```

Если нужно явно, укажите путь в config.yaml:

```yaml
colmap:
  executable: "C:/Users/<user>/anaconda3/envs/myenv/Library/bin/colmap.exe"
```

### Docker не запущен

Симптом:
- ошибка подключения к Docker daemon;
- `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`;
- `docker ps` не отвечает.

Решение: открыть Docker Desktop и повторить `docker ps`.

Проверьте также:

```bash
docker context show
docker info
```

Ожидается рабочий context (обычно `desktop-linux`) и успешный вывод `docker info`.

Если в `.env` есть строка ниже, закомментируйте или удалите:

```env
DOCKER_HOST=unix:///var/run/docker.sock
```

### ODM образ не найден

```bash
docker pull opendronemap/odm:latest
```

Или запускайте пайплайн сразу с автозагрузкой:

```bash
python -m src.ui.cli process-drone data/input/drone --pull-docker-image
```

### Конфликт имени контейнера ODM

Симптом (старые запуски):
- `Conflict. The container name "/odm_processor" is already in use`

Решение:

```bash
docker rm -f odm_processor
```

В актуальной версии проекта фиксированное имя контейнера для ODM больше не используется.

### Слишком долго или не хватает памяти

- Уменьшите число входных фото
- Запускайте без визуализации (`--no-visualization`)
- Используйте параметры фильтрации/даунсемплинга в config.yaml