# API Key Rotator 🔄

Простая, но мощная библиотека для автоматического вращения API ключей. Обходит лимиты запросов, обрабатывает ошибки 429 и делает ваши запросы неуязвимыми к ограничениям API.

## Особенности ✨

- 🔄 **Автоматическое вращение ключей** - Round-robin алгоритм
- ⚡ **Автодетект авторизации** - Сам определяет Bearer/API-Key формат
- 🔁 **Умные ретраи** - Экспоненциальная задержка при ошибках
- 🛡️ **Обработка ошибок** - 429, 500, 502, 503, 504 автоматически
- 💻 **Полная совместимость** с библиотекой `requests`
- 📝 **Понятные ошибки** - Подсказки как исправить проблемы

## Установка 📦

```bash
pip install apikeyrotator
```

Или из исходников:

```bash
git clone https://github.com/PrimeevolutionZ/apikeyrotator.git
cd apikeyrotator
pip install -e .
```

## Быстрый старт 🚀

### Способ 1: Передача ключей напрямую

```python
from apikeyrotator import APIKeyRotator

# Просто передайте ключи списком
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Или строкой через запятую
rotator = APIKeyRotator(api_keys="key1,key2,key3")

# Используйте как обычный requests!
response = rotator.get("https://api.example.com/data")
print(response.json())
```

### Способ 2: Использование переменных окружения

Создайте файл `.env` в корне проекта:
```env
API_KEYS=your_key_1,your_key_2,your_key_3
```

Или установите переменную окружения:
```bash
# Linux/Mac
export API_KEYS="your_key_1,your_key_2,your_key_3"

# Windows
set API_KEYS=your_key_1,your_key_2,your_key_3
```

Теперь просто инициализируйте ротатор:
```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator()  # Автоматически найдет API_KEYS

response = rotator.get("https://api.example.com/data")
```

## Примеры использования 📖

### Базовые HTTP-запросы

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# GET запрос
response = rotator.get("https://api.example.com/users")

# POST запрос с данными
response = rotator.post(
    "https://api.example.com/users",
    json={"name": "John", "email": "john@example.com"}
)

# PUT запрос
response = rotator.put(
    "https://api.example.com/users/1",
    json={"name": "John Updated"}
)

# DELETE запрос
response = rotator.delete("https://api.example.com/users/1")
```

### Кастомные заголовки авторизации

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

# Кастомный заголовок авторизации
response = rotator.get(
    "https://api.example.com/data",
    headers={"X-Custom-Auth": "custom_value"}
)

# Или переопределите авторизацию полностью
response = rotator.get(
    "https://api.example.com/data",
    headers={"Authorization": "Custom your_token_here"}
)
```

### Работа с параметрами запроса

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Параметры запроса
response = rotator.get(
    "https://api.example.com/search",
    params={"query": "python", "limit": 10}
)

# JSON данные
response = rotator.post(
    "https://api.example.com/items",
    json={"name": "New Item", "price": 99.99}
)

# Таймаут
response = rotator.get(
    "https://api.example.com/data",
    timeout=10
)
```

### Обработка ошибок

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2"], max_retries=5)

try:
    response = rotator.get("https://api.example.com/limited")
    print("Успех!", response.json())
except AllKeysExhaustedError as e:
    print("Все ключи исчерпаны:", e)
except Exception as e:
    print("Другая ошибка:", e)
```

## Расширенные настройки ⚙️

### Кастомизация параметров

```python
from apikeyrotator import APIKeyRotator

# Все параметры настройки
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],  # Ключи
    env_var="CUSTOM_API_KEYS",          # Кастомная переменная окружения
    max_retries=5,                      # Максимум попыток
    base_delay=2.0                      # Базовая задержка между попытками
)

print(f"Количество ключей: {len(rotator)}")
print(f"Максимум попыток: {rotator.max_retries}")
```

### Интеграция с существующим кодом

```python
from apikeyrotator import APIKeyRotator
import requests

# Существующий код с requests
response = requests.get("https://api.example.com/data")

# Легко замените на APIKeyRotator
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
response = rotator.get("https://api.example.com/data")  # Тот же API!
```

## Best Practices ✅

### 1. Используйте переменные окружения для безопасности

```bash
# Никогда не храните ключи в коде!
# Вместо этого используйте .env файл или переменные окружения
export API_KEYS="your_production_key_1,your_production_key_2"
```

### 2. Настройте адекватное количество попыток

```python
# Для 3 ключей и 2 попыток на ключ = 6 всего попыток
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=6
)
```

### 3. Мониторинг использования ключей

```python
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# После нескольких запросов можно посмотреть статистику
for i in range(10):
    rotator.get("https://api.example.com/test")

print("Ротатор отработал", len(rotator), "запросов")
```

## Обработка ошибок ❌

Библиотека предоставляет понятные сообщения об ошибках:

### Если ключи не найдены

```
❌ No API keys found.
   Please either:
   1. Pass keys directly: APIKeyRotator(api_keys=['key1', 'key2'])
   2. Set environment variable: export API_KEYS='key1,key2'
   3. Create .env file with: API_KEYS=key1,key2
```

### Если все ключи исчерпаны

```python
try:
    response = rotator.get("https://api.example.com/limited")
except AllKeysExhaustedError as e:
    print(e)  # "All 3 keys exhausted after 6 attempts"
```

## Совместимость 🔄

- **Python**: 3.7+
- **Зависимости**: только `requests>=2.25.0`

## Разработка 🛠️

### Установка для разработки

```bash
git clone https://github.com/PrimeevolutionZ/apikeyrotator.git
cd apikeyrotator
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
pip install -e .[dev]
```

### Запуск тестов

```bash
pytest tests/
```

### Сборка пакета

```bash
python setup.py sdist bdist_wheel
```

## Лицензия 📄

MIT License - смотрите файл [LICENSE](LICENSE) для деталей.

## Поддержка 🤝

Нашли баг или есть предложения? [Создайте issue](https://github.com/yourusername/apikeyrotator/issues) на GitHub!

---

**API Key Rotator** - сделайте ваши API запросы неуязвимыми к ограничениям! 🚀