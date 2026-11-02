# DNS Checker (Android)

Поиск DNS-сервера, через который `gemini.google.com` доступен из РФ с зарубежной геолокацией.

## Что внутри

- `main.py` — GUI на Kivy (таблица: сервер, IP, DNS ms, TTFB ms, HTTP-статус, код страны).
- `checker_core.py` — вся логика: DNS-запросы (UDP/DoT/DoH), HTTPS-проба, разбор кода страны. Работает и в десктопном python, и на андроиде.
- `buildozer.spec` — конфиг сборки.
- `.github/workflows/build.yml` — автосборка APK в облаке.

## Запуск на GitHub Actions (рекомендуется)

1. Залей репозиторий на GitHub.
2. Actions → build-apk → Run workflow.
3. Скачай APK из артефактов вкладки (раздел Artifacts).

## Локальная сборка (опционально)

Нужен Linux (или WSL) с Python 3.10+ и apk-цепочкой:

```bash
pip install buildozer
sudo apt update && sudo apt install -y autoconf automake autopoint build-essential \
  ccache git libtool libncurses5-dev libssl-dev libtinfo5 python3-venv zlib1g-dev
buildozer android debug
```

Готовый файл появится в `bin/*.apk`.