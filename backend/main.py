from fastapi import FastAPI

app = FastAPI(title="Mahabharata Guide API")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
