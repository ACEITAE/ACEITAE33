from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase_config import supabase

app = FastAPI(title="ACEITAÊ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Usuario(BaseModel):
    nome: str
    email: str
    telefone: str
    tipo: str
    senha: str
    cpf: Optional[str] = None
    pix: Optional[str] = None
    endereco: Optional[str] = None

class LoginData(BaseModel):
    email: str
    senha: str

@app.post("/cadastrar")
def cadastrar(user: Usuario):
    existing = supabase.table("usuarios").select("*").eq("email", user.email).execute()
    if existing.data:
        raise HTTPException(400, "E-mail já cadastrado")
    supabase.table("usuarios").insert(user.dict()).execute()
    return {"mensagem": "Cadastro realizado com sucesso!"}

@app.post("/login")
def login(credenciais: LoginData):
    result = supabase.table("usuarios").select("*").eq("email", credenciais.email).eq("senha", credenciais.senha).execute()
    if not result.data:
        raise HTTPException(401, "E-mail ou senha inválidos")
    user = result.data[0]
    return {
        "usuario_id": user["id"],
        "nome": user["nome"],
        "tipo": user["tipo"]
    }

@app.get("/")
def root():
    return {"mensagem": "ACEITAÊ está no ar!"}

@app.get("/health")
def health():
    return {"status": "online"}
