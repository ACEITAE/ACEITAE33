from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase_config import supabase
import uuid
import hashlib
import time
import re
from urllib.parse import quote
from datetime import datetime

app = FastAPI(title="ACEITAÊ API", version="3.0.0")

# CORS - totalmente aberto
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
    whatsapp: Optional[str] = None

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
# FUNÇÃO PARA GERAR LINK DO WHATSAPP (MELHORADA)
# ==================================================

def gerar_link_whatsapp(telefone: str, mensagem: str):
    """
    Gera link direto para WhatsApp com mensagem pré-preenchida
    """
    # Remove caracteres não numéricos
    numero = re.sub(r'\D', '', telefone)
    
    # Adiciona 55 se não tiver
    if not numero.startswith('55'):
        numero = '55' + numero
    
    # Garante que tem pelo menos 12 dígitos (55 + DDD + número)
    if len(numero) == 12:  # 55 + 2 (DDD) + 8 números
        # Adiciona 9 na frente
        numero = numero[:4] + '9' + numero[4:]
    
    mensagem_codificada = quote(mensagem)
    return f"https://wa.me/{numero}?text={mensagem_codificada}"


def gerar_mensagem_oferta(produto_nome: str, valor_ofertado: float, comprador_nome: str, valor_pretendido: float):
    """
    Gera a mensagem personalizada para o vendedor
    """
    diferenca = valor_pretendido - valor_ofertado
    comissao = valor_ofertado * 0.10
    valor_liquido = valor_ofertado - comissao
    
    if diferenca > 0:
        texto_diferenca = f"⚠️ *{diferenca:.2f} abaixo* do seu valor pretendido"
    else:
        texto_diferenca = "✅ *Igual ou superior* ao seu valor pretendido"
    
    mensagem = f"""🛒 *NOVA OFERTA no ACEITAÊ!*

📦 *Produto:* {produto_nome}
💰 *Valor ofertado:* R$ {valor_ofertado:.2f}
👤 *Comprador:* {comprador_nome}

{texto_diferenca}
Valor pretendido: R$ {valor_pretendido:.2f}

📊 *Simulação:*
• Comissão ACEITAÊ (10%): R$ {comissao:.2f}
• Você receberá: R$ {valor_liquido:.2f}

🔗 *Para ACEITAR ou RECUSAR, acesse:*
https://aceitae.com.br/vendedor.html

⚠️ Oferta condicionada à sua aceitação. Você tem 48h para decidir."""
    
    return mensagem


# ==================================================
# ROTAS DE USUÁRIO (CORRIGIDAS)
# ==================================================

@app.post("/cadastrar")
def cadastrar(user: Usuario):
    # Verifica se e-mail já existe
    existing = supabase.table("usuarios").select("*").eq("email", user.email).execute()
    if existing.data:
        raise HTTPException(400, "E-mail já cadastrado")
    
    # 🔧 DICIONÁRIO EXPLÍCITO - GARANTE A COLUNA CORRETA DO WHATSAPP
    usuario_data = {
        "nome": user.nome,
        "email": user.email,
        "telefone": user.telefone,
        "tipo": user.tipo,
        "senha": user.senha,
        "cpf": user.cpf,
        "pix": user.pix,
        "endereco": user.endereco,
        "whatsapp": user.whatsapp,  # ← EXPLÍCITO, VAI PARA A COLUNA CERTA
        "criado_em": datetime.now().isoformat()
    }
    
    # LOG PARA DEBUG
    print(f"📝 ========================================")
    print(f"📝 CADASTRANDO NOVO USUÁRIO:")
    print(f"   Nome: {user.nome}")
    print(f"   Email: {user.email}")
    print(f"   WhatsApp: {user.whatsapp}")
    print(f"   Tipo: {user.tipo}")
    print(f"📝 ========================================")
    
    # Insere o usuário com dicionário explícito
    result = supabase.table("usuarios").insert(usuario_data).execute()
    
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
        "tipo": user["tipo"],
        "whatsapp": user.get("whatsapp", "")
    }


@app.get("/usuarios/{usuario_id}/whatsapp")
def obter_whatsapp_usuario(usuario_id: int):
    """Endpoint para obter WhatsApp do usuário"""
    result = supabase.table("usuarios").select("whatsapp").eq("id", usuario_id).execute()
    if not result.data:
        raise HTTPException(404, "Usuário não encontrado")
    
    whatsapp = result.data[0].get("whatsapp", "")
    print(f"📞 WhatsApp do usuário {usuario_id}: {whatsapp}")
    
    return {"whatsapp": whatsapp}


@app.put("/usuarios/{usuario_id}/whatsapp")
def atualizar_whatsapp(usuario_id: int, whatsapp: str):
    """Atualiza o WhatsApp do usuário"""
    result = supabase.table("usuarios").update({"whatsapp": whatsapp}).eq("id", usuario_id).execute()
    if not result.data:
        raise HTTPException(404, "Usuário não encontrado")
    
    print(f"✅ WhatsApp atualizado: usuário {usuario_id} -> {whatsapp}")
    
    return {"mensagem": "WhatsApp atualizado com sucesso!", "whatsapp": whatsapp}


# ==================================================
# ROTA DE TESTE WHATSAPP
# ==================================================

@app.get("/test-whatsapp/{vendedor_id}")
def testar_whatsapp(vendedor_id: int):
    """Rota de teste para verificar se o WhatsApp está cadastrado"""
    vendedor = supabase.table("usuarios").select("whatsapp, nome, email").eq("id", vendedor_id).execute()
    
    if not vendedor.data:
        return {"erro": "Vendedor não encontrado"}
    
    if not vendedor.data[0].get("whatsapp"):
        return {
            "erro": "WhatsApp não cadastrado",
            "vendedor": vendedor.data[0]["nome"],
            "whatsapp": None,
            "acao": "Cadastre o WhatsApp no perfil do vendedor"
        }
    
    telefone = vendedor.data[0]["whatsapp"]
    numero_limpo = re.sub(r'\D', '', telefone)
    if not numero_limpo.startswith('55'):
        numero_limpo = '55' + numero_limpo
    
    return {
        "vendedor": vendedor.data[0]["nome"],
        "email": vendedor.data[0]["email"],
        "whatsapp_original": telefone,
        "whatsapp_formatado": numero_limpo,
        "link_teste": f"https://wa.me/{numero_limpo}?text=Teste%20ACEITA%C3%8A%20-%20sua%20notifica%C3%A7%C3%A3o%20est%C3%A1%20funcionando!",
        "instrucao": "Clique no link_teste para ver se chega no seu WhatsApp"
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
# ROTAS DE OFERTA (COM NOTIFICAÇÃO WHATSAPP)
# ==================================================

@app.post("/ofertas")
def fazer_oferta(oferta: Oferta, comprador_id: int, comprador_nome: str):
    # Busca o produto
    produto = supabase.table("produtos").select("*").eq("id", oferta.produto_id).execute()
    if not produto.data:
        raise HTTPException(404, "Produto não encontrado")
    
    produto = produto.data[0]
    
    if produto["status"] != "aprovado":
        raise HTTPException(400, "Produto não está disponível para ofertas")
    
    valor_pretendido = produto["valor_pretendido"]
    valor_oferta = oferta.valor
    
    # Verifica se já existe oferta pendente do mesmo comprador
    oferta_existente = supabase.table("ofertas").select("*")\
        .eq("produto_id", oferta.produto_id)\
        .eq("comprador_id", comprador_id)\
        .eq("status", "pendente").execute()
    
    if oferta_existente.data:
        raise HTTPException(400, "Você já tem uma oferta pendente para este produto")
    
    # Determina status da oferta
    if valor_oferta >= valor_pretendido:
        status_oferta = "venda_automatica"
        supabase.table("produtos").update({"status": "vendido"}).eq("id", oferta.produto_id).execute()
        mensagem = f"✅ Venda automática! Produto vendido por R$ {valor_oferta:.2f}"
    else:
        status_oferta = "pendente"
        mensagem = f"🟡 Oferta condicional enviada! Aguardando vendedor decidir"
    
    # Cria a oferta
    nova_oferta = {
        "produto_id": oferta.produto_id,
        "comprador_id": comprador_id,
        "comprador_nome": comprador_nome,
        "valor": valor_oferta,
        "status": status_oferta,
        "condicional": valor_oferta < valor_pretendido,
        "valor_pretendido": valor_pretendido,
        "criado_em": datetime.now().isoformat()
    }
    
    result = supabase.table("ofertas").insert(nova_oferta).execute()
    oferta_id = result.data[0]["id"]
    
    # ================================================
    # ENVIA NOTIFICAÇÃO WHATSAPP (se vendedor tiver cadastrado)
    # ================================================
    link_whatsapp = None
    
    # Busca o WhatsApp do vendedor
    vendedor_info = supabase.table("usuarios").select("whatsapp, nome").eq("id", produto["vendedor_id"]).execute()
    
    print(f"🔍 DEBUG: Vendedor ID: {produto['vendedor_id']}")
    print(f"🔍 DEBUG: Vendedor info: {vendedor_info.data}")
    
    if vendedor_info.data:
        whatsapp_vendedor = vendedor_info.data[0].get("whatsapp")
        print(f"🔍 DEBUG: WhatsApp encontrado: {whatsapp_vendedor}")
        
        if whatsapp_vendedor:
            telefone = whatsapp_vendedor
            
            # Gera a mensagem personalizada
            mensagem_whatsapp = gerar_mensagem_oferta(
                produto_nome=produto["nome"],
                valor_ofertado=valor_oferta,
                comprador_nome=comprador_nome,
                valor_pretendido=valor_pretendido
            )
            
            # Gera o link do WhatsApp
            link_whatsapp = gerar_link_whatsapp(telefone, mensagem_whatsapp)
            
            print(f"🔔 ========================================")
            print(f"📱 NOTIFICAÇÃO WHATSAPP GERADA!")
            print(f"📦 Produto: {produto['nome']}")
            print(f"💰 Valor ofertado: R$ {valor_oferta:.2f}")
            print(f"💰 Valor pretendido: R$ {valor_pretendido:.2f}")
            print(f"👤 Comprador: {comprador_nome}")
            print(f"📞 WhatsApp vendedor: {telefone}")
            print(f"🔗 Link: {link_whatsapp}")
            print(f"🔔 ========================================")
        else:
            print(f"⚠️ Vendedor não tem WhatsApp cadastrado!")
    else:
        print(f"❌ Vendedor não encontrado na tabela usuários!")
    
    return {
        "mensagem": mensagem,
        "oferta_id": oferta_id,
        "status": status_oferta,
        "notificationLink": link_whatsapp
    }


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
                "produto_descricao": produto.get("descricao", ""),
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
        if not arquivo.content_type.startswith("image/"):
            raise HTTPException(400, "Formato inválido. Envie uma imagem.")
        
        conteudo = await arquivo.read()
        
        if len(conteudo) > 10 * 1024 * 1024:
            raise HTTPException(400, "Arquivo muito grande (máx 10MB)")
        
        extensao = arquivo.filename.split(".")[-1].lower()
        if extensao not in ["jpg", "jpeg", "png", "gif", "webp"]:
            extensao = "jpg"
        
        nome_arquivo = f"{uuid.uuid4()}.{extensao}"
        
        supabase.storage.from_("produtos").upload(
            nome_arquivo,
            conteudo,
            file_options={"content-type": arquivo.content_type}
        )
        
        url = supabase.storage.from_("produtos").get_public_url(nome_arquivo)
        
        if not url.startswith("https://"):
            url = f"https://{url}"
        
        return {"url": url, "mensagem": "Upload realizado com sucesso!"}
        
    except Exception as e:
        print(f"Erro no upload: {str(e)}")
        raise HTTPException(400, detail=str(e))


# ==================================================
# ADMIN: LISTAR PRODUTOS PENDENTES
# ==================================================

@app.get("/admin/produtos/pendentes")
def listar_produtos_pendentes():
    result = supabase.table("produtos").select("*").eq("status", "aguardando_vistoria").execute()
    return {"produtos": result.data, "total": len(result.data)}


@app.put("/admin/produtos/{produto_id}/aprovar")
def admin_aprovar_produto(produto_id: int):
    result = supabase.table("produtos").update({"status": "aprovado"}).eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(404, "Produto não encontrado")
    return {"mensagem": "Produto aprovado com sucesso!"}


@app.put("/admin/produtos/{produto_id}/reprovar")
def admin_reprovar_produto(produto_id: int):
    result = supabase.table("produtos").update({"status": "reprovado"}).eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(404, "Produto não encontrado")
    return {"mensagem": "Produto reprovado!"}


# ==================================================
# ROTAS BÁSICAS
# ==================================================

@app.get("/")
def root():
    return {"mensagem": "ACEITAÊ está no ar!"}


@app.get("/health")
def health():
    return {"status": "online"}
