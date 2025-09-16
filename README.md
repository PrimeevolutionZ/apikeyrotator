# 🔁 APIKeyRotator — Обход лимитов бесплатных API через ротацию ключей

> 🚀 Python-библиотека для автоматического переключения между API-ключами при достижении лимитов.  
> Идеально подходит для OpenAI, SerpAPI, DeepL, ElevenLabs и других сервисов с ограничениями на бесплатный тариф.

---

## ✨ Зачем это нужно?

Многие API-сервисы ограничивают количество запросов на один ключ (например, 3 RPM или 5000 токенов в минуту).  
С `APIKeyRotator` вы можете:

- Указать **несколько ключей** в `.env`
- Библиотека будет **автоматически переключаться** между ними при ошибках (например, `429 Too Many Requests`)
- **Распределить нагрузку** — ключи используются по кругу
- **Увеличить пропускную способность** без перехода на платный тариф

---

## 🚀 Установка

```bash
pip install apikeyrotator
```
---

Или установите локально (если клонировали репозиторий):
```bash
git clone https://github.com/PrimeevolutionZ/apikeyrotator.git
cd apikeyrotator
pip install -e .
```
⚙️ Быстрый старт
1. Создайте файл .env в корне вашего проекта:
```bash
API_KEYS=sk-yourkey1,sk-yourkey2,sk-yourkey3
```
>✅ Ключи можно получить в личных кабинетах сервисов (OpenAI, SerpAPI и т.д.) 
2. Используйте в коде:
```python
from apikeyrotator import APIKeyRotator

# Функция, которая формирует заголовки с ключом
def make_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

# Инициализация ротатора
rotator = APIKeyRotator()

# Пример запроса к OpenAI
try:
    response = rotator.request_with_rotation(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers_fn=make_headers,
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Привет, как дела?"}]
        }
    )
    print("✅ Успешный ответ:", response.status_code)
    print(response.json())

except Exception as e:
    print("❌ Ошибка:", e)
```
---
>❗ Обработка ошибок
Библиотека выбрасывает понятные исключения:
```python
from apikeyrotator.exceptions import NoAPIKeysError, APIKeyExhaustedError

try:
    response = rotator.request_with_rotation(...)
except NoAPIKeysError:
    print("❌ Не найдены API ключи — проверьте .env файл!")
except APIKeyExhaustedError:
    print("❌ Все ключи исчерпаны — запрос не удался.")
except Exception as e:
    print(f"❌ Другая ошибка: {e}")
```
---
В конце концов надеюсь получилось что то адекватное. 