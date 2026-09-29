# NXToolBox

[English](README.md) | **Русский**

Набор инструментов на Python для Nintendo Switch (homebrew, Atmosphere). NXToolBox
запускает скрипты MicroPython на консоли и даёт им доступ к железу: кнопкам, стикам,
сенсорному экрану, вибрации, графике 1280×720, файлам, сети, последовательным портам и
другим USB-устройствам, USB-клавиатуре и мыши. Скрипты запускаются со стартового экрана
на консоли, редактируются во встроенном редакторе или отправляются с компьютера, а их
вывод в реальном времени показывается в терминале.

## Возможности

- **Стартовый экран на Python:** скрипты в виде плиток с иконками, вкладка **System** с
  информацией о консоли, вкладка **USB** с деревом подключённых USB-интерфейсов, вкладка
  **USB Drive** для просмотра USB-флешки (FAT) и копирования файлов на SD-карту, вкладка
  **Settings**, вкладка **Docs** (инструкция и справочник по модулям, рендерятся из
  Markdown, список страниц слева) и вкладка **About**, вкладки переключаются L и R. Его
  можно менять без пересборки.
- **Темы:** тёмная и светлая (цвета JetBrains) или свои ini-файлы; плавные скругления углов
  с настраиваемым радиусом.
- **Редактор скриптов на консоли:** подсветка синтаксиса, номера строк, автоотступы, отмена,
  запуск по F5 с выводом в панели справа; при ошибке курсор переходит на её строку.
- **Запуск и загрузка с компьютера** под Windows, macOS или Linux (`send.py`, без
  зависимостей): вывод в реальном времени, остановка по Ctrl+C.
- **Get scripts:** установка скриптов с GitHub, по любой ссылке или из каталогов скриптов.
- **Онлайн-обновления** стартового экрана и библиотек из вашего репозитория.
- **Остановка любого скрипта:** `+` и `-` вместе на консоли, Ctrl+C на компьютере или HOME.
- **Защита паролем** (HMAC-SHA256 с одноразовым запросом; сам пароль по сети не передаётся).
- **API для скриптов:** железо (`switch`), графика (`gfx`, `image`), интерфейс с раскладками
  как в Qt (`ui`, `tabs`), USB-клавиатура и мышь (`keys`), HTTP(S) (`requests`),
  последовательные порты и USB-устройства (`usbserial`, `usbhid`, `usbhost`), USB-флешки
  (`usbmsc`, `fat`), информация о консоли (`sysinfo`), файлы и `import`.

## Содержание

- [Требования](#требования)
- [Сборка](#сборка)
- [Первый запуск](#первый-запуск)
- [Работа с NXToolBox](#работа-с-nxtoolbox)
- [Запуск скриптов с компьютера](#запуск-скриптов-с-компьютера)
- [Написание скриптов](#написание-скриптов)
- [Разработка](#разработка)
- [Решение проблем](#решение-проблем)
- [Безопасность](#безопасность)
- [Сторонние компоненты](#сторонние-компоненты)

## Требования

- Switch, на которой запускается homebrew с Atmosphere. Используйте emuMMC и не выходите в
  сеть с CFW.
- [devkitPro](https://devkitpro.org) с пакетами `switch-dev` и `switch-curl`
  (`sudo dkp-pacman -S switch-dev switch-curl`) и заданной переменной `DEVKITPRO`
  (обычно `/opt/devkitpro`).
- [MicroPython](https://github.com/micropython/micropython) версии 1.20 или новее,
  склонированный рядом с проектом (`../micropython`) или в любое другое место с переменной
  `MICROPYTHON_DIR`.
- Python 3.8+ на компьютере.

## Сборка

### Однократная настройка

1. **stb_image** (декодирование растровых картинок для иконок плиток) и **nanosvg**
   (иконки SVG) в папку `source/`:
   ```
   curl -L -o source/stb_image.h https://raw.githubusercontent.com/nothings/stb/master/stb_image.h
   curl -L -o source/nanosvg.h https://raw.githubusercontent.com/memononen/nanosvg/master/src/nanosvg.h
   curl -L -o source/nanosvgrast.h https://raw.githubusercontent.com/memononen/nanosvg/master/src/nanosvgrast.h
   ```
2. **cacert.pem** (доверенные центры сертификации для HTTPS; в хранилище самой консоли нет
   некоторых современных корневых сертификатов) в корень проекта, со страницы
   https://curl.se/docs/caextract.html. Файл упаковывается в приложение и обновляется онлайн.
3. **update_url.txt** (необязательно, включает онлайн-обновления): одна строка с прямой
   ссылкой на `update.json` в вашем репозитории, например
   ```
   https://raw.githubusercontent.com/artem14133q/nxtoolbox/refs/heads/master/update.json
   ```
4. **Makefile**: скопируйте шаблон devkitPro
   (`cp $DEVKITPRO/examples/switch/templates/application/Makefile .`) и измените:
   ```make
   TARGET   := NXToolBox
   SOURCES  := source modules/switch micropython_embed/py micropython_embed/extmod micropython_embed/shared/runtime micropython_embed/port
   INCLUDES := source modules/switch micropython_embed
   LIBS     := -lcurl -lz -lnx -lm
   ROMFS    := romfs
   ```
   и сделайте так, чтобы перед сборкой упаковывались Python-файлы:
   ```make
   $(BUILD): bundle
   	@[ -d $@ ] || mkdir -p $@
   	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

   .PHONY: bundle
   bundle:
   	@python3 tools/bundle.py
   ```

### Сборка

```
./gen.sh                  # ядро MicroPython; повторять после изменений в modules/ или mpconfigport.h
make clean && make        # -> NXToolBox.nro
```

Если менялись только `source/*.c`, достаточно `make`. Изменённые Python-файлы из `app/` и
`lib/` `make` упакует заново сам.

Скопируйте `NXToolBox.nro` в `/switch/` на SD-карте и запускайте из меню homebrew, лучше
удерживая R при запуске игры: так приложение получает больше памяти и работает системная
клавиатура.

## Первый запуск

- Приложение создаёт пароль, показывает его на вкладке System и в текстовом меню и
  сохраняет в `/switch/NXToolBox/password.txt` (удалите файл, чтобы получить новый).
- Стартовый экран и библиотеки, упакованные в .nro, устанавливаются в
  `/switch/NXToolBox/sys/`. Более новая сборка заменяет их автоматически, а версия,
  установленная онлайн, сохраняется, даже если потом запустить более старый .nro.

## Работа с NXToolBox

### Стартовый экран

Под заголовком три вкладки, переключаются **L** и **R**:

- **Files**: скрипты из `/switch/NXToolBox/scripts` в виде плиток; папки открываются,
  скрипты запускаются.
- **System**: модель, серийный номер (Y показывает его), версия прошивки и Atmosphere,
  emuMMC или sysMMC, заряд и здоровье батареи, температуры, вентилятор, частоты, память,
  сеть, время.
- **Settings**: тема и скругление углов (применяется сразу).

| Кнопка | Вкладка Files | Во время работы скрипта | После скрипта |
|---|---|---|---|
| Крестовина / касание | выбор | | |
| A | открыть папку / запустить скрипт | | |
| B | на уровень выше | | назад на стартовый экран |
| ZR | редактировать выбранный скрипт | | |
| ZL | создать новый скрипт | | |
| Y | обновить | | |
| X | удалить выбранный файл | | |
| L / R | переключить вкладку | | |
| + | выйти из приложения | | |
| + и - вместе | | остановить скрипт | |

**Get scripts...** (кнопка на вкладке Files) устанавливает скрипты по ссылке на файл, папку
(`.../tree/ВЕТКА/папка`) или репозиторий на GitHub, по любой прямой ссылке или из каталога
скриптов.

Если стартовый экран упал, приложение показывает ошибку и переключается на встроенное
текстовое меню; **X** в нём снова пробует запустить стартовый экран. Если при запуске
приложения удерживать **-**, стартовый экран будет пропущен.

### Плитки

Скрипт описывает свою плитку переменной. Чтобы прочитать её, файл не выполняется,
допускаются только литералы:

```python
__NXTOOLBOX_MODULE__ = {
    "title": "Snake",
    "description": "Classic snake game",
    "icon": "snake.png",      # путь относительно скрипта: PNG, JPEG, BMP, GIF или SVG
    "version": "1.0",
}
```

Скрипты без иконки получают цветную букву; у папки показывается её `icon.png`, если он есть.

### Редактор скриптов

ZR открывает выбранный скрипт, ZL создаёт новый по шаблону.

- **F5** запускает текст прямо в редакторе: `print` выводится в панель справа, строка с
  ошибкой подсвечивается, и курсор переходит на неё.
- **Ctrl+F5** сохраняет файл и запускает скрипт на весь экран в чистом интерпретаторе.
  Используйте его для скриптов с графикой, своими экранами или USB-устройствами, а также
  после правки модулей, которые скрипт импортирует (F5 использует уже загруженные модули).
- USB-клавиатура: стрелки, Home/End, PgUp/PgDn, Ctrl+S — сохранить, Ctrl+Z — отменить,
  Ctrl+плюс/минус — масштаб, Esc — закрыть. Мышь ставит курсор и прокручивает текст.
- Только Joy-Con: крестовина двигает курсор, A редактирует строку системной клавиатурой,
  Y добавляет строку, X удаляет её, ZR запускает, ZL отменяет, `+` сохраняет, B закрывает.

### Темы

Встроенные темы — **Dark** и **Light** (цвета JetBrains New UI, включая подсветку синтаксиса
в редакторе). Тема — это ini-файл: скопируйте `themes/dark.ini` в
`/switch/NXToolBox/themes/<имя>.ini`, поменяйте нужные цвета (остальные возьмутся из тёмной
темы) и выберите её на вкладке Settings:

```ini
[theme]
name = Моя тема
radius = 8

[colors]
accent = #E06C75

[editor]
keyword = #C678DD
```

Выбор хранится в `/switch/NXToolBox/settings.ini` (`theme`, `radius`; радиус 0 — прямые
углы). Скрипты получают тот же стиль через `ui`: `ui.ACCENT`, `ui.TEXT`...,
`ui.box(x, y, w, h, цвет)` для скруглённых панелей и `ui.set_rounded(r)`.

### Каталоги скриптов

Каталог — это `index.json` на любом веб-сервере. Его можно собрать из папки со скриптами
(одна подпапка или `.py`-файл на пакет; необязательный `nxtoolbox.json` с названием,
версией, описанием и главным файлом):

```
python3 tools/make_catalog.py my-catalog --name "Мои скрипты"
```

Разместите его на GitHub (`https://raw.githubusercontent.com/OWNER/REPO/main/index.json`)
или у себя (`python3 -m http.server 8000` в папке каталога) и добавьте ссылку в
Get scripts -> Add a catalog. Switch покажет названия, версии и описания, установит и
обновит пакеты и сможет сразу их запустить.

### Онлайн-обновления

При каждом запуске приложения стартовый экран один раз проверяет `update_url.txt` и
предлагает установить новую версию стартового экрана, библиотек и `cacert.pem`. Чтобы
выпустить обновление, соберите проект (это перепишет `update.json` с версией по времени
последнего изменения файлов), затем закоммитьте и запушьте `update.json`, `cacert.pem`,
`app/launcher.py` и `lib/`.

### Файлы на SD-карте

```
/switch/NXToolBox/
├── sys/            встроенные launcher.py, lib/, themes/, cacert.pem, VERSION (управляет приложение)
├── launcher.py     необязательно: ваш стартовый экран, важнее sys/launcher.py
├── lib/            ваши модули, важнее sys/lib (быстрые правки без пересборки)
├── scripts/        скрипты стартового экрана; рабочая папка запущенного скрипта
├── themes/         ваши темы (<имя>.ini)
├── settings.ini    выбранная тема и радиус скругления
├── catalogs.txt    каталоги скриптов ("Название | URL" в каждой строке)
├── installed.json  установленные пакеты из каталогов и их версии
└── password.txt    удалите, чтобы сгенерировать новый пароль
```

В скриптах `/` — это корень SD-карты (пути вида `sdmc:/` не работают).

## Запуск скриптов с компьютера

Один раз задайте адрес и пароль:

```
# macOS / Linux (~/.zshrc или ~/.bashrc)
export NXTOOLBOX_HOST=192.168.1.42
export NXTOOLBOX_PASSWORD=yourpassword

# Windows
setx NXTOOLBOX_HOST 192.168.1.42
setx NXTOOLBOX_PASSWORD yourpassword
```

Дальше (на Windows `py` вместо `python3`):

```
python3 send.py run examples/hwtest.py        # запустить и смотреть вывод; Ctrl+C останавливает
python3 send.py upload game.py                # -> /switch/NXToolBox/scripts
python3 send.py upload mylib --to lib         # модули для import
python3 send.py upload app/launcher.py --to . # быстрая правка стартового экрана
python3 send.py screenshot -o shot.png        # сохранить PNG того, что сейчас на экране
python3 send.py input button A --hold 100     # имитировать нажатие A на 100 мс
python3 send.py input tap 640 360             # имитировать касание в точке (640, 360)
python3 send.py input swipe 640 600 640 200   # имитировать свайп (например, для скролла)
python3 send.py input release                 # сразу отменить любой ожидающий фейковый ввод
```

После загрузки `launcher.py` или `lib/ui.py` стартовый экран сразу перезапускается.
Удалите свои копии в `/switch/NXToolBox/`, чтобы вернуться к встроенным версиям.

`screenshot` работает, только пока активен графический режим (стартовый экран или скрипт
с GUI) - кадр читается напрямую из C, поэтому неважно, чем в этот момент занят интерпретатор.

`input` имитирует нажатия и касания для автотестов: ведёте интерфейс через `input`,
проверяете результат через `screenshot`. Это надстройка НАД реальными кнопками/тачем
(`switch.buttons()`, `switch.touches()` и т.д.), а не их замена — реальный ввод продолжает
работать одновременно. Единственное сознательное исключение: физическая комбинация
**+ и - вместе**, которая аварийно останавливает зависший скрипт, всегда читает реальное
железо напрямую и не может быть подделана по сети — человек у консоли всегда сохраняет
контроль.

## Написание скриптов

Полные сигнатуры и документация — в `stubs/*.pyi` (подсказки для IDE) и в начале каждого
файла в `lib/`.

### Железо (`switch`)

```python
import switch

switch.buttons()            # зажатые кнопки: switch.buttons() & switch.A
switch.buttons_down()       # нажатые с прошлого вызова
switch.stick(0)             # (x, y) левого стика от -1.0 до 1.0; 1 — правый стик
switch.touches()            # [(x, y), ...] в портативном режиме
switch.rumble(0.5, 300)     # сила, длительность в мс (0 — до вызова rumble(0))
switch.keyboard("", "Имя")  # системная клавиатура -> str или None
switch.battery()            # заряд в процентах
switch.ticks_ms()           # миллисекунды с момента включения
switch.sleep_ms(16)         # пауза, которую можно прервать
switch.running()            # вызывать в каждом цикле; False — приложение закрывается
```

### Графика (`gfx`, `image`)

```python
import gfx, image

while switch.running():
    gfx.clear(gfx.rgb(20, 24, 40))
    gfx.fill_circle(640, 360, 50, gfx.RED)
    gfx.text(20, 20, "Hello / Привет", gfx.WHITE, scale=2)
    w, h, rgba = image.load("logo.png", 256, 256)   # PNG/JPEG/BMP/GIF/SVG, вписывается в размер
    gfx.blit(100, 100, w, h, rgba)
    gfx.present()                                   # показать кадр, ~60 кадров/с
```

Первый же вызов рисования переключает экран в графический режим. Когда скрипт
завершается, возвращается текстовая консоль со всем, что скрипт напечатал.

### Интерфейс (`ui`, `tabs`)

```python
import ui

scr = ui.Screen("Настройки")
form = ui.Grid()
form.add(ui.Label("Громкость"), 0, 0)
level = form.add(ui.Slider(value=30, maximum=100), 0, 1)
form.set_column_stretch(1, 1)

buttons = ui.HBox()
buttons.add(ui.Button("Сохранить", on_click=lambda: ui.message("Сохранено: %d" % level.value)))
buttons.add_stretch()

root = ui.VBox()
root.add(form)
root.add(buttons)
root.add_stretch()
scr.set_layout(root)
scr.run()

ui.confirm("Удалить файл?")                # True / False
ui.choose("Выберите", ["A", "B", "C"])     # индекс или None
```

Виджеты: `Label`, `Button`, `Checkbox`, `Slider`, `ProgressBar`, `ListBox` и `TileGrid`
(`lib/tiles.py`). Раскладки: `VBox`, `HBox`, `Grid`, их можно вкладывать друг в друга.
`tabs.TabScreen` добавляет вкладки с переключением L и R. Крестовина, A/B и касания
работают везде. Цвета и скругления берутся из выбранной темы; `ui.box()` и `ui.circle()`
рисуют плавные скруглённые фигуры.

### USB-клавиатура и мышь (`keys`)

```python
import keys

kb, mouse = keys.Keyboard(), keys.Mouse()   # английская и русская раскладки, Alt+Shift
while switch.running():
    for ev in kb.poll():                    # нажатия и автоповтор
        if ev.char:
            text += ev.char
        elif ev.code == keys.ENTER:
            ...
    m = mouse.poll()                        # x, y, dx, dy, wheel, buttons, pressed, released
```

Работает поверх системной поддержки клавиатуры/мыши (`usbinput`), которая видит устройства
только на USB-портах дока - переходник USB-C OTG в портативном режиме не распознаётся.

### Сеть (`requests`, `installer`)

```python
import requests
r = requests.get("https://api.github.com/repos/micropython/micropython")
print(r.status_code, r.json()["stargazers_count"])
requests.download("https://example.com/data.bin", "data.bin")

import installer
installer.install_url("https://github.com/OWNER/REPO/tree/main/tools")
```

### Последовательные порты и USB-устройства (`usbserial`, `usbhid`, `usbhost`)

```python
from usbserial import Serial
with Serial(baudrate=115200) as port:   # USB-Serial: CDC-ACM или CH340
    port.write("on\n")
    print(port.readline(timeout=1000))

import usbhid
with usbhid.HID(vid=0x1234) as dev:
    report = dev.read(timeout=100)

import usbhost                          # любое другое доступное устройство:
print(usbhost.devices())                # control-, bulk- и interrupt-передачи
```

Подключайте устройства к USB-портам дока или через переходник USB-C OTG в портативном
режиме. Скриптам доступны не все USB-устройства: устройства класса HID (клавиатуры, мыши,
геймпады и другие HID-устройства) и всё, что распознаёт sys-con, система оставляет себе.
Устройства с vendor-specific интерфейсом (класс 0xFF) работают через `usbhost`.

### USB-флешки (`usbmsc`, `fat`)

USB-накопители (mass storage) система тоже не забирает себе, поэтому скрипты могут
работать с ними напрямую: `usbmsc` говорит по SCSI поверх Bulk-Only Transport (блочный
доступ, только чтение), а `fat` — это написанный на чистом Python драйвер FAT12/16/32
только для чтения (без exFAT) поверх него. Вкладка **USB Drive** в лаунчере использует
те же два модуля, чтобы показывать содержимое флешки и копировать файлы на SD-карту.

```python
import usbmsc, fat

drive = usbmsc.Drive(usbmsc.drives()[0])
vol = fat.mount(drive)                  # читает MBR/boot-сектор, определяет FAT12/16/32
for entry in vol.listdir():             # [{"name", "dir", "size"}, ...]
    print(entry["name"], entry["size"])
with vol.open("DCIM/100GOPRO/photo.jpg") as f:
    data = f.read()
vol.close()
```

### Информация о консоли (`sysinfo`)

`sysinfo.read()` возвращает словарь с моделью, прошивкой, батареей, температурами,
частотами, памятью, сетью и временем; неизвестные значения равны `None`.

### Примеры

| Скрипт | Что показывает |
|---|---|
| `examples/hwtest.py` | батарея, кнопки, стики, касания, вибрация |
| `examples/buttons.py` | простая работа с кнопками |
| `examples/files.py` | файлы и импорт |
| `examples/forever.py` | бесконечный цикл для проверки остановки |
| `examples/gfx_demo.py` | графика: мячи, управление стиком, FPS |
| `examples/gfx_paint.py` | рисование пальцами на сенсорном экране |
| `examples/ui_demo.py` | виджеты, раскладки и диалоги |
| `examples/kbm_test.py` | USB-клавиатура и мышь |
| `examples/usb_list.py` | доступные USB-интерфейсы |
| `examples/usb_serial_test.py` | последовательный порт: отправка команд и вывод ответов |
| `examples/usb_hid_test.py` | вывод HID-отчётов |
| `examples/usb_drive_test.py` | подключает USB-флешку, выводит файлы деревом |

## Разработка

### Структура проекта

```
NXToolBox/
├── source/                 исходники на C (libnx): main.c, *_hw.c, mp_glue.c, mpconfigport.h
├── modules/switch/         C-модули MicroPython: switch, usbhost, gfx, nxapp, http,
│                           sysinfo, image, usbinput (+ gfx_font.h)
├── app/launcher.py         стартовый экран
├── lib/                    библиотеки на Python: ui, theme, tabs, tiles, systab, usbtab, usbdisk_tab,
│                           usbmsc, fat, settings_tab, docs_tab, about_tab, markdown, textview, editor, keys,
│                           modinfo, requests, installer, store, usbserial, usbhid
├── themes/                 dark.ini, light.ini (упаковываются в приложение)
├── examples/               примеры и тестовые скрипты
├── stubs/                  .pyi-файлы для подсказок в IDE
├── tools/                  bundle.py, make_catalog.py, make_font.py,
│                           gen_compile_commands.py
├── licenses/               лицензии сторонних компонентов
├── gen.sh                  генерирует micropython_embed/
├── send.py                 запуск скриптов / загрузка файлов с компьютера
├── update.json             манифест онлайн-обновлений (пишет tools/bundle.py)
└── update_url.txt          прямая ссылка на update.json в вашем репозитории
```

Код на C написан в стандарте C23 (GCC 15 в devkitA64 по умолчанию использует `gnu23`).
Новые C-модули состоят из `modules/switch/mod*.c` (сторона MicroPython, без заголовков
libnx) и `source/*_hw.c` (сторона libnx); добавьте их в `modules/switch/micropython.mk` и
выполните `./gen.sh`.

### CLion

```
python3 tools/gen_compile_commands.py
```

Затем **File -> Open -> compile_commands.json -> Open as Project**. После `./gen.sh` или
добавления `.c`-файлов снова запустите скрипт и выберите
**Tools -> Compilation Database -> Reload**. Для подсказок в Python отметьте папку `stubs/`
как Sources Root.

### Протокол

`send.py` общается с приложением по TCP, порт 5555. Switch отправляет случайное число,
клиент отвечает HMAC-SHA256(пароль, число) и командой: `R` (запустить скрипт, вывод
передаётся обратно; закрытие передающей стороны вызывает KeyboardInterrupt) или `U`
(загрузить файл по пути относительно `/switch/NXToolBox`; он пишется во временный файл и
переименовывается после завершения).

## Решение проблем

| Проблема | Причина и решение |
|---|---|
| HTTPS: «SSL peer certificate ... was not OK» | Проверьте дату и время на консоли; положите `cacert.pem` в корень проекта и пересоберите (или загрузите его в `/switch/NXToolBox/`). |
| USB-устройства нет в списке | Его забрал sys-con или система. Отключите sys-con (`/atmosphere/contents/690000000000000D/flags/boot2.flag`); устройства класса HID остаются у системы, используйте устройство с vendor-specific интерфейсом. |
| Не открывается системная клавиатура | Запускайте меню homebrew, удерживая R на игре, а не из Альбома. |
| Кириллица обрезается посреди букв | Включите `MICROPY_PY_BUILTINS_STR_UNICODE` в `source/mpconfigport.h` и пересоберите. |
| «invalid syntax» на строке с `"\u..."` | Без поддержки Unicode работают только коды меньше 256; пишите сам символ. |
| Не запускается стартовый экран | Удерживайте `-` при запуске приложения, исправьте `launcher.py`, нажмите X в текстовом меню. |
| `undefined reference` после добавления модуля | Добавьте его в `micropython.mk`, выполните `./gen.sh`, затем `make clean && make`. |

## Безопасность

- Загрузка и скачивание файлов ограничены папкой `/switch/NXToolBox/`; пути с `..`
  отклоняются.
- Скрипты имеют доступ ко всей SD-карте. Не пишите в `atmosphere/`, `emuMMC/` и `Nintendo/`.
- Пароль защищает от запуска чужого кода, но скрипты и их вывод не шифруются.
- Скрипты из интернета — это обычный код: устанавливайте только то, чему доверяете. Плитки
  читают `__NXTOOLBOX_MODULE__`, не запуская скрипт.

## Сторонние компоненты

- [MicroPython](https://micropython.org) — лицензия MIT, скачивается отдельно.
- [libnx](https://github.com/switchbrew/libnx) и инструменты devkitPro — ISC и другие лицензии.
- [libcurl](https://curl.se) (пакет devkitPro `switch-curl`) — лицензия curl.
- [stb_image](https://github.com/nothings/stb) — общественное достояние / MIT, скачивается
  отдельно.
- [nanosvg](https://github.com/memononen/nanosvg) — лицензия zlib, скачивается отдельно,
  см. `licenses/NANOSVG.txt`.
- Глифы шрифта из [GNU Unifont](https://unifoundry.com/unifont/) — SIL OFL 1.1 /
  GPLv2+ с исключением для встраивания шрифтов, см. `licenses/UNIFONT.txt`.
- `cacert.pem` — список корневых сертификатов Mozilla в том виде, в каком его публикует
  проект curl.
