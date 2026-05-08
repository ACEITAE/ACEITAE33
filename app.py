from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase_config import supabase
import uuid
import hashlib
import time
from datetime import datetime

app = FastAPI(title="ACEITAÊ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# MODELOS
# ==================================================

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

class Produto(BaseModel):
    nome: str
    descricao: str
    categoria: str
    valor_pretendido: float
    fotos: Optional[list] = []
    video: Optional[str] = None

class Oferta(BaseModel):
    produto_id: int
    valor: float

# ==================================================
# FUNÇÃO PARA GERAR TOKEN SIMPLES
# ==================================================

def gerar_token(user_id: int, email: str):
    token_data = f"{user_id}:{email}:{time.time()}"
    return hashlib.sha256(token_data.encode()).hexdigest()

# ==================================================
# ROTAS DE USUÁRIO
# ==================================================

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
    
    # Gerar token
    access_token = gerar_token(user["id"], user["email"])
    
    return {
        "access_token": access_token,
        "usuario_id": user["id"],
        "nome": user["nome"],
        "tipo": user["tipo"]
    }

# ==================================================
# ROTAS DE PRODUTO
# ==================================================

@app.post("/produtos")
def criar_produto(produto: Produto, vendedor_id: int):
    vendedor = supabase.table("usuarios").select("*").eq("id", vendedor_id).eq("tipo", "vendedor").execute()
    if not vendedor.data:
        raise HTTPException(404, "Vendedor não encontrado")
    
    valor_exposicao = round(produto.valor_pretendido * 1.10, 2)
    
    novo_produto = {
        "vendedor_id": vendedor_id,
        "vendedor_nome": vendedor.data[0]["nome"],
        "nome": produto.nome,
        "descricao": produto.descricao,
        "categoria": produto.categoria,
        "valor_pretendido": produto.valor_pretendido,
        "valor_exposicao": valor_exposicao,
        "status": "aguardando_vistoria",
        "fotos": produto.fotos or [],
        "video": produto.video,
        "criado_em": datetime.now().isoformat()
    }
    
    result = supabase.table("produtos").insert(novo_produto).execute()
    return {"produto_id": result.data[0]["id"], "mensagem": "Produto cadastrado! Aguardando vistoria."}

@app.get("/produtos")
def listar_produtos(status: Optional[str] = None, vendedor_id: Optional[int] = None):
    query = supabase.table("produtos").select("*")
    if status:
        query = query.eq("status", status)
    if vendedor_id:
        query = query.eq("vendedor_id", vendedor_id)
    result = query.execute()
    return {"produtos": result.data}

@app.put("/produtos/{produto_id}/aprovar")
def aprovar_produto(produto_id: int):
    result = supabase.table("produtos").update({"status": "aprovado"}).eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(404, "Produto não encontrado")
    return {"mensagem": "Produto aprovado!"}

# ==================================================
# ROTAS DE OFERTA
# ==================================================

@app.post("/ofertas")
def fazer_oferta(oferta: Oferta, comprador_id: int):
    produto = supabase.table("produtos").select("*").eq("id", oferta.produto_id).execute()
    if not produto.data:
        raise HTTPException(404, "Produto não encontrado")
    
    produto = produto.data[0]
    
    if produto["status"] != "aprovado":
        raise HTTPException(400, "Produto não está disponível para ofertas")
    
    comprador = supabase.table("usuarios").select("*").eq("id", comprador_id).execute()
    comprador_nome = comprador.data[0]["nome"] if comprador.data else "Anônimo"
    
    if oferta.valor >= produto["valor_pretendido"]:
        status_oferta = "venda_automatica"
        supabase.table("produtos").update({"status": "vendido"}).eq("id", oferta.produto_id).execute()
        mensagem = f"✅ Venda automática! Produto vendido por R$ {oferta.valor:.2f}"
    else:
        status_oferta = "pendente"
        mensagem = f"🟡 Oferta condicional enviada! Aguardando vendedor decidir"
    
    nova_oferta = {
        "produto_id": oferta.produto_id,
        "comprador_id": comprador_id,
        "comprador_nome": comprador_nome,
        "valor": oferta.valor,
        "status": status_oferta,
        "condicional": oferta.valor < produto["valor_pretendido"],
        "valor_pretendido": produto["valor_pretendido"],
        "criado_em": datetime.now().isoformat()
    }
    
    result = supabase.table("ofertas").insert(nova_oferta).execute()
    return {"mensagem": mensagem, "oferta_id": result.data[0]["id"], "status": status_oferta}

@app.put("/ofertas/{oferta_id}/responder")
def responder_oferta(oferta_id: int, acao: str):
    oferta = supabase.table("ofertas").select("*").eq("id", oferta_id).execute()
    if not oferta.data:
        raise HTTPException(404, "Oferta não encontrada")
    
    oferta = oferta.data[0]
    
    if oferta["status"] != "pendente":
        raise HTTPException(400, "Esta oferta já foi respondida")
    
    valor_oferta = oferta["valor"]
    comissao = round(valor_oferta * 0.10, 2)
    valor_liquido = round(valor_oferta - comissao, 2)
    
    if acao.upper() == "ACEITAÊ":
        supabase.table("ofertas").update({"status": "aceita"}).eq("id", oferta_id).execute()
        supabase.table("produtos").update({"status": "vendido"}).eq("id", oferta["produto_id"]).execute()
        mensagem = f"🎉 ACEITAÊ! Venda confirmada!\nValor: R$ {valor_oferta:.2f}\nComissão (10%): R$ {comissao:.2f}\nVocê receberá: R$ {valor_liquido:.2f}"
        return {"mensagem": mensagem, "status": "aceita"}
    elif acao.upper() == "RECUSAR":
        supabase.table("ofertas").update({"status": "recusada"}).eq("id", oferta_id).execute()
        return {"mensagem": "❌ Oferta recusada", "status": "recusada"}
    else:
        raise HTTPException(400, "Ação inválida. Use 'ACEITAÊ' ou 'RECUSAR'")

@app.get("/vendedor/{vendedor_id}/ofertas")
def listar_ofertas_vendedor(vendedor_id: int):
    produtos = supabase.table("produtos").select("*").eq("vendedor_id", vendedor_id).execute()
    if not produtos.data:
        return {"ofertas": []}
    
    produtos_ids = [p["id"] for p in produtos.data]
    ofertas = supabase.table("ofertas").select("*").in_("produto_id", produtos_ids).execute()
    
    resultado = []
    for oferta in ofertas.data:
        produto = next((p for p in produtos.data if p["id"] == oferta["produto_id"]), None)
        if produto:
            resultado.append({
                "oferta_id": oferta["id"],
                "produto_nome": produto["nome"],
                "comprador_nome": oferta["comprador_nome"],
                "valor_ofertado": oferta["valor"],
                "valor_pretendido": oferta["valor_pretendido"],
                "status": oferta["status"],
                "criado_em": oferta["criado_em"]
            })
    return {"ofertas": resultado}

# ==================================================
# UPLOAD DE FOTOS
# ==================================================

@app.post("/upload-foto")
async def upload_foto(arquivo: UploadFile = File(...)):
    try:
        # Aceita qualquer tipo de imagem
        if not arquivo.content_type.startswith("image/"):
            raise HTTPException(400, "Formato inválido. Envie uma imagem.")
        
        conteudo = await arquivo.read()
        
        # Limite de 10MB
        if len(conteudo) > 10 * 1024 * 1024:
            raise HTTPException(400, "Arquivo muito grande (máx 10MB)")
        
        # Pega extensão correta
        extensao = arquivo.filename.split(".")[-1].lower()
        if extensao not in ["jpg", "jpeg", "png", "gif", "webp"]:
            extensao = "jpg"
        
        nome_arquivo = f"{uuid.uuid4()}.{extensao}"
        
        # Upload para o Supabase
        supabase.storage.from_("produtos").upload(
            nome_arquivo,
            conteudo,
            file_options={"content-type": arquivo.content_type}
        )
        
        # Gera URL pública
        url = supabase.storage.from_("produtos").get_public_url(nome_arquivo)
        
        # Garante que a URL está completa
        if not url.startswith("https://"):
            url = f"https://{url}"
        
        return {"url": url, "mensagem": "Upload realizado com sucesso!"}
        
    except Exception as e:
        print(f"Erro no upload: {str(e)}")
        raise HTTPException(400, detail=str(e))
# ==================================================
# ROTAS BÁSICAS
# ==================================================

@app.get("/")
def root():
    return {"mensagem": "ACEITAÊ está no ar!"}

@app.get("/health")
def health():
    return {"status": "online"}
