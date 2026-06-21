content = '''from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router

app = FastAPI(
    title="Unhoused Matchmaker API",
    description="AI-powered social worker to shelter matching for Hawaii",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"}
    )

app.include_router(router, prefix="/api")

@app.get("/")
def root():
    return {"status": "online", "message": "Unhoused Matchmaker API is live"}
'''
with open("app/main.py", "w", encoding="utf-8", newline="\n") as f:
    f.write(content)
print("Done")
