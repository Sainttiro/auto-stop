# Настройка GitHub для Auto-Stop

## 1. Создание репозитория

1. Перейдите на https://github.com/new
2. Название: `auto-stop`
3. Тип: **Public** (для бесплатных GitHub Actions)
4. Не добавляйте README, .gitignore, license (уже есть в проекте)
5. Нажмите **Create repository**

## 2. Настройка Secrets

1. Перейдите в Settings → Secrets and variables → Actions
2. Нажмите **New repository secret**
3. Добавьте следующие секреты:

### SERVER_HOST
- Name: `SERVER_HOST`
- Value: IP адрес вашего сервера (например: `192.168.0.144`)

### SERVER_USER
- Name: `SERVER_USER`
- Value: имя пользователя на сервере (например: `user`)

### SERVER_PORT
- Name: `SERVER_PORT`
- Value: порт SSH (например: `2222`)

### SERVER_SSH_KEY
- Name: `SERVER_SSH_KEY`
- Value: приватный SSH ключ

#### Создание SSH ключа для GitHub Actions

На вашем компьютере:

```bash
# Создание нового SSH ключа
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions_key

# Копирование публичного ключа
cat ~/.ssh/github_actions_key.pub
```

На сервере:

```bash
# Добавление публичного ключа в authorized_keys
nano ~/.ssh/authorized_keys
# Вставьте содержимое github_actions_key.pub
# Сохраните (Ctrl+O, Enter, Ctrl+X)

# Установка правильных прав
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

Скопируйте приватный ключ для GitHub Secret:

```bash
cat ~/.ssh/github_actions_key
# Скопируйте весь вывод (включая BEGIN и END)
```

## 3. Первый push

```bash
cd /path/to/auto-stop

# Инициализация git (если еще не сделано)
git init
git add .
git commit -m "Initial commit"

# Добавление remote
git remote add origin https://github.com/yourusername/auto-stop.git

# Push
git branch -M main
git push -u origin main
```

## 4. Создание первого релиза

```bash
# Создание тега
git tag v1.0.0

# Push тега
git push origin v1.0.0
```

Или через веб-интерфейс:
1. Перейдите в Releases
2. Нажмите **Create a new release**
3. Tag: `v1.0.0`
4. Title: `v1.0.0 - Initial Release`
5. Description: описание изменений
6. Нажмите **Publish release**

## 5. Проверка деплоя

1. Перейдите в Actions
2. Найдите workflow "Build and Deploy Release"
3. Проверьте статус выполнения
4. При ошибках проверьте логи

## 6. Настройка GitHub Container Registry

Образы автоматически публикуются в `ghcr.io/yourusername/auto-stop`

Для использования образов:
1. Они публичные, если репозиторий публичный
2. Автоматически доступны для pull

## Готово!

Теперь при каждом создании релиза система автоматически обновится на сервере.
