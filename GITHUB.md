# Как выложить на GitHub (шпаргалка)

Если с Git раньше не работал — вот минимум команд.

## Разово: установить и представиться

Скачай Git с https://git-scm.com, потом:

```bash
git config --global user.name "Твоё Имя"
git config --global user.email "твой@email"
```

## Создать репозиторий и первый коммит

В папке проекта:

```bash
git init
git add .
git commit -m "Первый коммит: калькулятор, сканер, матчер, бэктест"
```

## Залить на GitHub

1. На https://github.com нажми **New repository**, назови `polymarket-ev`,
   создай **пустой** (без README — он у тебя уже есть).
2. GitHub покажет ссылку вида `https://github.com/USER/polymarket-ev.git`.
3. Выполни:

```bash
git branch -M main
git remote add origin https://github.com/USER/polymarket-ev.git
git push -u origin main
```

## Дальше — обычный цикл

```bash
git add .
git commit -m "что изменил"
git push
```

## Полезное

Создай файл `.gitignore`, чтобы не заливать мусор и свои данные сигналов:

```
__pycache__/
*.pyc
signals.csv
.venv/
```
