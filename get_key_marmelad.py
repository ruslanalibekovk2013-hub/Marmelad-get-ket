# -*- coding: utf-8 -*-
"""
Бэкенд для SyntaxAI: выдаёт свежие рабочие ключи OpenRouter по запросу с сайта.

КАК ЗАПУСТИТЬ НА PYTHONANYWHERE:
1. Зайди на pythonanywhere.com -> Web -> Add a new web app -> Flask.
2. Открой Files, найди файл вида flask_app.py (или свой существующий проект,
   если бот/сайт уже развёрнут) и вставь туда содержимое этого файла
   (или создай отдельное Flask-приложение специально под этот эндпоинт).
3. Впиши свой Management API ключ OpenRouter в MANAGEMENT_API_KEY ниже
   (тот, что ты создал на openrouter.ai/settings/keys, раздел "Management Keys").
4. Во вкладке Web нажми Reload.
5. Проверь: POST https://твойлогин.pythonanywhere.com/api/get-key
   должен вернуть JSON вида {"key": "sk-or-v1-..."}.
6. В файле constructor/syntaxai HTML пропиши этот же URL в константе
   KEY_BACKEND_URL.

ВАЖНО ПРО БЕЗОПАСНОСТЬ:
- MANAGEMENT_API_KEY даёт полный доступ к управлению всеми ключами твоего
  аккаунта OpenRouter. Он должен быть только здесь, на сервере.
  Никогда не вставляй его в HTML/JS.
- Раздавать ключи "всем подряд" без ограничений опасно — любой посетитель
  сайта сможет тратить твой баланс OpenRouter. Ниже уже есть базовая защита:
    * каждому новому ключу ставится небольшой кредитный лимит (KEY_CREDIT_LIMIT);
    * простой rate-limit по IP, чтобы один человек не наштамповал 100 ключей подряд.
  Это не защита военного уровня, но для небольшого личного проекта достаточно.
  Для более серьёзной защиты добавь проверку авторизации пользователя
  (например, по твоей существующей системе профиля/баланса в SyntaxAI),
  чтобы ключ выдавался один раз на аккаунт, а не бесконечно.
"""

import os
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# ---------------- НАСТРОЙКИ ----------------

# Твой Management API ключ с openrouter.ai/settings/keys ("Management Keys").
# ВАЖНО: ключ НЕ хранится в коде — он берётся из переменной окружения
# MANAGEMENT_API_KEY, которую нужно задать в настройках хостинга (Render:
# Environment Variables). Так ключ не попадает в открытый репозиторий на GitHub.
MANAGEMENT_API_KEY = os.environ.get("MANAGEMENT_API_KEY", "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")

# Лимит в долларах на каждый выданный ключ (защита от слива баланса).
# Поставь None, если лимит не нужен.
KEY_CREDIT_LIMIT = 1.0

# Сколько ключей разрешено получить с одного IP за сутки.
MAX_KEYS_PER_IP_PER_DAY = 3

# --------------------------------------------

_issued_by_ip = {}  # {ip: [timestamp, timestamp, ...]}


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    day_ago = now - 24 * 60 * 60
    history = [t for t in _issued_by_ip.get(ip, []) if t > day_ago]
    _issued_by_ip[ip] = history
    return len(history) >= MAX_KEYS_PER_IP_PER_DAY


def _record_issue(ip: str):
    _issued_by_ip.setdefault(ip, []).append(time.time())


def _cors(resp):
    # Разрешаем запросы с любого источника (упрости/ужесточи при необходимости,
    # например замени "*" на "https://твой-сайт.com")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/api/get-key", methods=["POST", "OPTIONS"])
def get_key():
    if request.method == "OPTIONS":
        return _cors(app.make_default_options_response())

    if not MANAGEMENT_API_KEY:
        return _cors(jsonify({
            "error": "MANAGEMENT_API_KEY не задан на сервере (переменная окружения пуста)."
        })), 500

    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

    if _is_rate_limited(ip):
        return _cors(jsonify({
            "error": "Слишком много запросов с этого адреса. Попробуй завтра."
        })), 429

    payload = {"name": f"syntaxai_user_{int(time.time())}"}
    if KEY_CREDIT_LIMIT is not None:
        payload["limit"] = KEY_CREDIT_LIMIT

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/keys/",
            headers={
                "Authorization": f"Bearer {MANAGEMENT_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        new_key = data.get("key")
        if not new_key:
            raise ValueError("OpenRouter не вернул ключ в ответе")
    except Exception as e:
        return _cors(jsonify({"error": f"Не удалось создать ключ: {e}"})), 502

    _record_issue(ip)
    return _cors(jsonify({"key": new_key}))


if __name__ == "__main__":
    app.run(debug=True)
