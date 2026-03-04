from fastapi import FastAPI

app = FastAPI()


@app.get("/image-query")
def image_query():
    return {"message": "hello world"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
