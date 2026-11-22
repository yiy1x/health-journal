import json
import os
from pathlib import Path
import sys
import time


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    config = {}
    for argument in sys.argv[1:]:
        if "=" not in argument:
            continue
        key, value = argument.split("=", 1)
        target = config
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = json.loads(value)
    scenario = os.environ.get("HEALTH_FAKE_CASE", "normal")
    trace = Path(os.environ["HEALTH_FAKE_TRACE"])
    account = None
    login_pending = False
    with trace.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"environment": dict(os.environ), "cwd": os.getcwd(), "argv": sys.argv[1:]}) + "\n")
    for line in sys.stdin:
        request = json.loads(line)
        with trace.open("a", encoding="utf-8") as output:
            output.write(json.dumps(request) + "\n")
        method = request["method"]
        params = request.get("params", {})
        if "id" not in request:
            continue
        result = {}
        if method == "initialize":
            if scenario == "duplicate-json":
                print('{"id":1,"id":1,"result":{}}', flush=True)
                continue
            if scenario == "oversized":
                print("x" * (13 * 1024 * 1024 + 1), flush=True)
                continue
            if scenario == "bad-notification":
                emit({"method": "account/updated", "params": []})
                continue
            if scenario == "server-request":
                emit({"method": "item/commandExecution/requestApproval", "id": "tool-1", "params": {}})
                continue
            if scenario == "error":
                emit({"id": request["id"], "error": {"message": "synthetic-SECRET-MUST-NOT-LEAK"}})
                continue
            if scenario == "exit":
                return
        elif method == "config/read":
            if scenario == "unsafe-config":
                config["sandbox_mode"] = "danger-full-access"
            if scenario == "bool-config":
                config["analytics"]["enabled"] = 0
            result = {"config": config}
        elif method == "account/read":
            if login_pending:
                account = {"type": "chatgpt", "email": "synthetic@example.invalid", "planType": "plus"}
                if scenario == "api-account":
                    account = {"type": "apiKey"}
                login_pending = False
                emit({"method": "account/updated", "params": {}})
            result = {"account": account}
        elif method == "account/login/start":
            login_pending = True
            result = {"loginId": "synthetic-login", "authUrl": "https://auth.openai.com/authorize?synthetic=offline-only"}
            if scenario == "bad-auth-url":
                result["authUrl"] = "https://auth.openai.com.evil.invalid/"
        elif method == "account/login/cancel":
            login_pending = False
        elif method == "account/logout":
            login_pending = False
            account = None
            emit({"method": "account/updated", "params": {}})
        elif method == "model/list":
            modalities = "image" if scenario == "bad-model" else ["text", "image"]
            result = {"data": [{"model": "synthetic-vision", "displayName": "离线合成模型（非真实服务）", "inputModalities": modalities}, {"model": "synthetic-text", "displayName": "合成文字模型", "inputModalities": ["text"]}]}
        elif method == "thread/start":
            result = {"thread": {"id": "synthetic-thread"}, "modelProvider": "openai", "model": params["model"], "approvalPolicy": "never", "sandbox": {"type": "readOnly"}}
            if scenario == "wrong-thread":
                result["sandbox"]["type"] = "dangerFullAccess"
        elif method == "turn/start":
            emit({"id": request["id"], "result": {"turn": {"id": "synthetic-turn"}}})
            if scenario == "hang":
                time.sleep(60)
                continue
            if scenario == "delay":
                time.sleep(2)
            identifiers = {"threadId": "synthetic-thread", "turnId": "synthetic-turn"}
            emit({"method": "item/started", "params": {**identifiers, "item": {"type": "userMessage", "id": "input", "content": params["input"]}}})
            if scenario == "tool":
                emit({"method": "item/started", "params": {**identifiers, "item": {"type": "commandExecution", "id": "never-authorized"}}})
                continue
            if scenario == "auth-change":
                emit({"method": "account/updated", "params": {}})
            task = json.loads(params["input"][0]["text"])["task"]
            answer = {"summary": "【离线合成验收，非真实模型输出】合成草稿", "uncertainties": ["需要人工核对"], "questions": []}
            if task == "document":
                answer.update(departments=[{"name": "内分泌科", "evidence": "合成原文含血糖"}], excerpts=[{"title": "血糖", "quote": "血糖 5.0 mmol/L", "location": "第1行", "department": "内分泌科"}])
            else:
                answer["suggestions"] = ["核对原始资料"]
                if task == "breakfast":
                    answer["foods"] = [{"name": "合成鸡蛋", "portion": "不确定", "confidence": "low"}]
            content = "not json" if scenario == "bad-output" else json.dumps(answer, ensure_ascii=False)
            item = {"type": "agentMessage", "id": "answer-1", "phase": "final_answer", "text": content}
            emit({"method": "item/completed", "params": {**identifiers, "item": None if scenario == "malformed-item" else item}})
            if scenario == "two-answers":
                emit({"method": "item/completed", "params": {**identifiers, "item": {**item, "id": "answer-2"}}})
            emit({"method": "turn/completed", "params": {"threadId": "synthetic-thread", "turn": {"id": "synthetic-turn", "status": "failed" if scenario == "failed-turn" else "completed"}}})
            continue
        elif method == "synthetic/timeout":
            time.sleep(60)
            continue
        emit({"id": request["id"], "result": result})


if __name__ == "__main__":
    main()
