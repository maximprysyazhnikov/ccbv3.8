import os, time
def save_report(symbol: str, text: str) -> str:
    os.makedirs("reports", exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join("reports", f"{symbol}_{ts}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
