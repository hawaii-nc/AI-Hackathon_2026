from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

app = FastAPI(
    title='Unhoused Matchmaker API',
    description='AI-powered social worker to shelter matching for Hawaii',
    version='1.0.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router, prefix='/api')

@app.get('/')
def root():
    return {'status': 'online', 'message': 'Unhoused Matchmaker API is live'}
