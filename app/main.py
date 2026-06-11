from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"message": "Codebase Assistant API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}