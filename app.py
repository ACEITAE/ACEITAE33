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
# VERIFICAR SE USUÁRIO É ADMIN
# ==================================================

@app.get("/usuarios/{usuario_id}/is-admin")
def verificar_admin(usuario_id: int):
    """Verifica se o usuário é administrador"""
    try:
        result = supabase.table("usuarios").select("is_admin, tipo, email, nome").eq("id", usuario_id).execute()
        if not result.data:
            return {"is_admin": False, "erro": "Usuário não encontrado"}
        
        user = result.data[0]
        # Verifica se is_admin é True OU tipo é 'admin'
        is_admin = user.get("is_admin", False) or user.get("tipo") == "admin"
        
        return {
            "is_admin": is_admin,
            "email": user.get("email"),
            "nome": user.get("nome")
        }
    except Exception as e:
        print(f"Erro ao verificar admin: {str(e)}")
        return {"is_admin": False, "erro": str(e)}

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
# ROTAS PARA EDITAR E EXCLUIR PRODUTOS
# ==================================================

@app.put("/produtos/{produto_id}")
def atualizar_produto(produto_id: int, request: Request):
    """Atualiza os dados de um produto existente"""
    try:
        dados = request.json()
        
        # Verifica se o produto existe
        produto_existente = supabase.table("produtos").select("*").eq("id", produto_id).execute()
        if not produto_existente.data:
            raise HTTPException(404, "Produto não encontrado")
        
        # Prepara os dados para atualização (apenas campos enviados)
        dados_atualizados = {}
        
        if "nome" in dados:
            dados_atualizados["nome"] = dados["nome"]
        if "descricao" in dados:
            dados_atualizados["descricao"] = dados["descricao"]
        if "valor_pretendido" in dados:
            dados_atualizados["valor_pretendido"] = dados["valor_pretendido"]
            dados_atualizados["valor_exposicao"] = dados["valor_pretendido"] * 1.10
        if "condicao" in dados:
            dados_atualizados["condicao"] = dados["condicao"]
        if "quantidade" in dados:
            dados_atualizados["quantidade"] = dados["quantidade"]
        if "fotos" in dados:
            dados_atualizados["fotos"] = dados["fotos"]
        
        if not dados_atualizados:
            return {"mensagem": "Nenhum dado para atualizar"}
        
        # Atualiza no banco
        result = supabase.table("produtos").update(dados_atualizados).eq("id", produto_id).execute()
        
        return {"mensagem": "Produto atualizado com sucesso!", "produto": result.data[0]}
    except Exception as e:
        print(f"Erro ao atualizar produto: {str(e)}")
        raise HTTPException(500, str(e))


@app.delete("/produtos/{produto_id}")
def excluir_produto(produto_id: int):
    """Remove um produto do sistema"""
    try:
        # Verifica se o produto existe
        produto_existente = supabase.table("produtos").select("*").eq("id", produto_id).execute()
        if not produto_existente.data:
            raise HTTPException(404, "Produto não encontrado")
        
        # Remove as ofertas relacionadas primeiro (evita erro de chave estrangeira)
        supabase.table("ofertas").delete().eq("produto_id", produto_id).execute()
        
        # Remove o produto
        supabase.table("produtos").delete().eq("id", produto_id).execute()
        
        return {"mensagem": "Produto excluído com sucesso!"}
    except Exception as e:
        print(f"Erro ao excluir produto: {str(e)}")
        raise HTTPException(500, str(e))
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
# INTEGRAÇÃO ASAAS - PAGAMENTOS
# ==================================================

import os
import requests
from datetime import datetime, timedelta

# Configuração Asaas (já deve ter as variáveis no Render)
ASAAS_ENV = os.getenv("ASAAS_ENV", "sandbox")
ASAAS_API_KEY_SANDBOX = os.getenv("ASAAS_API_KEY_sandbox")
ASAAS_API_KEY_PROD = os.getenv("ASAAS_API_KEY_prod")

if ASAAS_ENV == "production":
    ASAAS_API_KEY = ASAAS_API_KEY_PROD
    ASAAS_URL = "https://www.asaas.com/api/v3"
else:
    ASAAS_API_KEY = ASAAS_API_KEY_SANDBOX
    ASAAS_URL = "https://sandbox.asaas.com/api/v3"

ASAAS_HEADERS = {
    "access_token": ASAAS_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print(f"🔐 Ambiente ASAAS: {ASAAS_ENV}")
print(f"🔑 Chave ASAAS: {ASAAS_API_KEY[:10]}..." if ASAAS_API_KEY else "❌ Chave não encontrada!")


def criar_cliente_asaas(nome, email, cpf_cnpj, telefone=None):
    """Cria um cliente no Asaas"""
    url = f"{ASAAS_URL}/customers"
    payload = {
        "name": nome,
        "email": email,
        "cpfCnpj": re.sub(r'\D', '', cpf_cnpj),
        "phone": telefone or "",
        "notificationDisabled": False
    }
    try:
        response = requests.post(url, json=payload, headers=ASAAS_HEADERS)
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cliente Asaas: {e}")
        return None


def criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento):
    """Cria uma cobrança PIX no Asaas"""
    url = f"{ASAAS_URL}/payments"
    payload = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": valor,
        "dueDate": data_vencimento,
        "description": descricao
    }
    try:
        response = requests.post(url, json=payload, headers=ASAAS_HEADERS)
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cobrança Asaas: {e}")
        return None


@app.post("/ofertas/{oferta_id}/gerar-pagamento")
def gerar_pagamento_oferta(oferta_id: int):
    """
    Gera um link de pagamento PIX para o comprador
    Esta rota é chamada quando o vendedor ACEITA a oferta
    """
    try:
        # Busca a oferta
        oferta = supabase.table("ofertas").select("*").eq("id", oferta_id).execute()
        if not oferta.data:
            raise HTTPException(404, "Oferta não encontrada")
        oferta = oferta.data[0]
        
        if oferta["status"] != "pendente":
            raise HTTPException(400, "Esta oferta já foi respondida")
        
        # Busca o comprador
        comprador = supabase.table("usuarios").select("*").eq("id", oferta["comprador_id"]).execute()
        if not comprador.data:
            raise HTTPException(404, "Comprador não encontrado")
        comprador = comprador.data[0]
        
        # Busca o produto
        produto = supabase.table("produtos").select("*").eq("id", oferta["produto_id"]).execute()
        if not produto.data:
            raise HTTPException(404, "Produto não encontrado")
        produto = produto.data[0]
        
        # Verifica se o comprador tem CPF
        if not comprador.get("cpf"):
            return {
                "erro": "comprador_sem_cpf",
                "mensagem": "O comprador precisa ter CPF cadastrado para gerar o pagamento."
            }
        
        # Cria ou busca cliente do comprador no Asaas
        if comprador.get("asaas_customer_id"):
            customer_id = comprador["asaas_customer_id"]
        else:
            cliente = criar_cliente_asaas(
                comprador["nome"],
                comprador["email"],
                comprador["cpf"],
                comprador.get("telefone")
            )
            if cliente and cliente.get("id"):
                customer_id = cliente["id"]
                supabase.table("usuarios").update({
                    "asaas_customer_id": customer_id
                }).eq("id", comprador["id"]).execute()
            else:
                return {"erro": "erro_asaas", "mensagem": "Erro ao criar cliente no Asaas"}
        
        # Cria cobrança PIX
        valor = oferta["valor"]
        data_vencimento = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        descricao = f"ACEITAÊ - {produto['nome']}"
        
        cobranca = criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento)
        
        if not cobranca or not cobranca.get("id"):
            return {"erro": "erro_cobranca", "mensagem": "Erro ao criar cobrança no Asaas"}
        
        # Atualiza a oferta com os dados da cobrança
        supabase.table("ofertas").update({
            "asaas_payment_id": cobranca.get("id"),
            "asaas_pix_qr_code": cobranca.get("pixQrCode"),
            "asaas_pix_payload": cobranca.get("pixPayload"),
            "status": "aguardando_pagamento"
        }).eq("id", oferta_id).execute()
        
        # Retorna os dados do PIX
        return {
            "sucesso": True,
            "mensagem": "Pagamento PIX gerado com sucesso!",
            "pix_qr_code": cobranca.get("pixQrCode"),
            "pix_payload": cobranca.get("pixPayload"),
            "valor": valor,
            "vencimento": data_vencimento
        }
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        raise HTTPException(500, str(e))


@app.post("/webhook-asaas")
async def webhook_asaas(request: Request):
    """Recebe notificações do Asaas quando um pagamento é confirmado"""
    try:
        data = await request.json()
        evento = data.get("event")
        payment_id = data.get("payment", {}).get("id")
        
        print(f"📩 Webhook recebido: {evento} - Payment ID: {payment_id}")
        
        if evento == "PAYMENT_CONFIRMED":
            # Busca a oferta com este payment_id
            oferta = supabase.table("ofertas").select("*").eq("asaas_payment_id", payment_id).execute()
            if oferta.data:
                # Marca como pago
                supabase.table("ofertas").update({
                    "status": "pago",
                    "pago_em": datetime.now().isoformat()
                }).eq("id", oferta.data[0]["id"]).execute()
                
                # Notifica o vendedor (você pode enviar WhatsApp aqui)
                print(f"✅ Pagamento confirmado para oferta {oferta.data[0]['id']}")
                
                return {"status": "ok", "message": "Pagamento confirmado"}
        
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return {"error": str(e)}


# ==================================================
# Pagamentos cartão
# ==================================================
# ==================================================
# INTEGRAÇÃO ASAAS - PAGAMENTOS (PIX + CARTÃO)
# ==================================================

import os
import requests
from datetime import datetime, timedelta

# Configuração Asaas (lê variáveis do Render)
ASAAS_ENV = os.getenv("ASAAS_ENV", "sandbox")
ASAAS_API_KEY_SANDBOX = os.getenv("ASAAS_API_KEY_sandbox")
ASAAS_API_KEY_PROD = os.getenv("ASAAS_API_KEY_prod")

if ASAAS_ENV == "production":
    ASAAS_API_KEY = ASAAS_API_KEY_PROD
    ASAAS_URL = "https://www.asaas.com/api/v3"
else:
    ASAAS_API_KEY = ASAAS_API_KEY_SANDBOX
    ASAAS_URL = "https://sandbox.asaas.com/api/v3"

ASAAS_HEADERS = {
    "access_token": ASAAS_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print(f"🔐 Ambiente ASAAS: {ASAAS_ENV}")
print(f"🔑 Chave ASAAS: {ASAAS_API_KEY[:10]}..." if ASAAS_API_KEY else "❌ Chave não encontrada!")


def criar_cliente_asaas(nome, email, cpf_cnpj, telefone=None):
    """Cria um cliente no Asaas"""
    url = f"{ASAAS_URL}/customers"
    payload = {
        "name": nome,
        "email": email,
        "cpfCnpj": re.sub(r'\D', '', cpf_cnpj),
        "phone": telefone or "",
        "notificationDisabled": False
    }
    try:
        response = requests.post(url, json=payload, headers=ASAAS_HEADERS)
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cliente Asaas: {e}")
        return None


def criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento):
    """Cria uma cobrança PIX no Asaas"""
    url = f"{ASAAS_URL}/payments"
    payload = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": valor,
        "dueDate": data_vencimento,
        "description": descricao
    }
    try:
        response = requests.post(url, json=payload, headers=ASAAS_HEADERS)
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cobrança PIX Asaas: {e}")
        return None


def criar_cobranca_cartao_asaas(customer_id, valor, descricao, parcelas=1, data_vencimento=None):
    """Cria uma cobrança com cartão de crédito no Asaas (1 a 12 parcelas)"""
    url = f"{ASAAS_URL}/payments"
    payload = {
        "customer": customer_id,
        "billingType": "CREDIT_CARD",
        "value": valor,
        "description": descricao,
        "installmentCount": parcelas,
        "installmentValue": round(valor / parcelas, 2) if parcelas > 1 else valor,
    }
    if data_vencimento:
        payload["dueDate"] = data_vencimento
    
    try:
        response = requests.post(url, json=payload, headers=ASAAS_HEADERS)
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cobrança cartão Asaas: {e}")
        return None


# ==================================================
# ROTA: GERAR PAGAMENTO (PIX ou CARTÃO)
# ==================================================

@app.post("/ofertas/{oferta_id}/gerar-pagamento")
def gerar_pagamento_oferta(oferta_id: int, metodo: str = "pix", parcelas: int = 1):
    """
    Gera pagamento PIX ou Cartão de Crédito para o comprador
    metodo: "pix" ou "cartao"
    parcelas: 1 a 12 (para cartão)
    """
    try:
        # Busca a oferta
        oferta = supabase.table("ofertas").select("*").eq("id", oferta_id).execute()
        if not oferta.data:
            raise HTTPException(404, "Oferta não encontrada")
        oferta = oferta.data[0]
        
        if oferta["status"] != "pendente":
            raise HTTPException(400, "Esta oferta já foi respondida")
        
        # Busca o comprador
        comprador = supabase.table("usuarios").select("*").eq("id", oferta["comprador_id"]).execute()
        if not comprador.data:
            raise HTTPException(404, "Comprador não encontrado")
        comprador = comprador.data[0]
        
        # Busca o produto
        produto = supabase.table("produtos").select("*").eq("id", oferta["produto_id"]).execute()
        if not produto.data:
            raise HTTPException(404, "Produto não encontrado")
        produto = produto.data[0]
        
        # Verifica CPF
        if not comprador.get("cpf"):
            return {
                "erro": "comprador_sem_cpf",
                "mensagem": "O comprador precisa ter CPF cadastrado para gerar o pagamento."
            }
        
        # Cria ou busca cliente do comprador no Asaas
        if comprador.get("asaas_customer_id"):
            customer_id = comprador["asaas_customer_id"]
        else:
            cliente = criar_cliente_asaas(
                comprador["nome"],
                comprador["email"],
                comprador["cpf"],
                comprador.get("telefone")
            )
            if cliente and cliente.get("id"):
                customer_id = cliente["id"]
                supabase.table("usuarios").update({
                    "asaas_customer_id": customer_id
                }).eq("id", comprador["id"]).execute()
            else:
                return {"erro": "erro_asaas", "mensagem": "Erro ao criar cliente no Asaas"}
        
        valor = oferta["valor"]
        descricao = f"ACEITAÊ - {produto['nome']}"
        data_vencimento = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        # ============================================
        # ESCOLHE O MÉTODO DE PAGAMENTO
        # ============================================
        
        if metodo.lower() == "pix":
            cobranca = criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento)
            
            if not cobranca or not cobranca.get("id"):
                return {"erro": "erro_cobranca", "mensagem": "Erro ao criar cobrança PIX no Asaas"}
            
            # Salva os dados do PIX
            supabase.table("ofertas").update({
                "asaas_payment_id": cobranca.get("id"),
                "asaas_pix_qr_code": cobranca.get("pixQrCode"),
                "asaas_pix_payload": cobranca.get("pixPayload"),
                "asaas_tipo_pagamento": "pix",
                "status": "aguardando_pagamento"
            }).eq("id", oferta_id).execute()
            
            return {
                "sucesso": True,
                "metodo": "pix",
                "mensagem": "Pagamento PIX gerado com sucesso!",
                "pix_qr_code": cobranca.get("pixQrCode"),
                "pix_payload": cobranca.get("pixPayload"),
                "valor": valor,
                "vencimento": data_vencimento
            }
            
        elif metodo.lower() == "cartao":
            # Valida parcelas
            if parcelas < 1 or parcelas > 12:
                parcelas = 1
            
            cobranca = criar_cobranca_cartao_asaas(customer_id, valor, descricao, parcelas, data_vencimento)
            
            if not cobranca or not cobranca.get("id"):
                return {"erro": "erro_cobranca", "mensagem": "Erro ao criar cobrança com cartão no Asaas"}
            
            # Salva os dados do cartão
            supabase.table("ofertas").update({
                "asaas_payment_id": cobranca.get("id"),
                "asaas_tipo_pagamento": "cartao",
                "asaas_parcelas": parcelas,
                "status": "aguardando_pagamento"
            }).eq("id", oferta_id).execute()
            
            return {
                "sucesso": True,
                "metodo": "cartao",
                "mensagem": f"Pagamento com cartão gerado com sucesso! Parcelas: {parcelas}x",
                "checkout_url": cobranca.get("checkoutUrl") or cobranca.get("url"),
                "valor": valor,
                "parcelas": parcelas,
                "vencimento": data_vencimento
            }
        else:
            return {"erro": "metodo_invalido", "mensagem": "Método inválido. Use 'pix' ou 'cartao'"}
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        raise HTTPException(500, str(e))


# ==================================================
# WEBHOOK ASAAS (CONFIRMA PAGAMENTO)
# ==================================================

@app.post("/webhook-asaas")
async def webhook_asaas(request: Request):
    """Recebe notificações do Asaas quando um pagamento é confirmado"""
    try:
        data = await request.json()
        evento = data.get("event")
        payment_id = data.get("payment", {}).get("id")
        
        print(f"📩 Webhook recebido: {evento} - Payment ID: {payment_id}")
        
        if evento == "PAYMENT_CONFIRMED":
            # Busca a oferta com este payment_id
            oferta = supabase.table("ofertas").select("*").eq("asaas_payment_id", payment_id).execute()
            if oferta.data:
                # Marca como pago
                supabase.table("ofertas").update({
                    "status": "pago",
                    "pago_em": datetime.now().isoformat()
                }).eq("id", oferta.data[0]["id"]).execute()
                
                # Busca vendedor para notificar
                produto = supabase.table("produtos").select("*").eq("id", oferta.data[0]["produto_id"]).execute()
                if produto.data:
                    vendedor = supabase.table("usuarios").select("whatsapp").eq("id", produto.data[0]["vendedor_id"]).execute()
                    if vendedor.data and vendedor.data[0].get("whatsapp"):
                        msg = f"✅ Pagamento confirmado! Envie o produto: {produto.data[0]['nome']}"
                        link = gerar_link_whatsapp(vendedor.data[0]["whatsapp"], msg)
                        print(f"🔗 Notificar vendedor: {link}")
                
                print(f"✅ Pagamento confirmado para oferta {oferta.data[0]['id']}")
                return {"status": "ok", "message": "Pagamento confirmado"}
        
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return {"error": str(e)}

# ==================================================
# ROTAS BÁSICAS
# ==================================================

@app.get("/")
def root():
    return {"mensagem": "ACEITAÊ está no ar!"}


@app.get("/health")
def health():
    return {"status": "online"}
