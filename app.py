from fastapi import FastAPI, HTTPException, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase_config import supabase
import uuid
import hashlib
import time
import re
import os
from urllib.parse import quote
from datetime import datetime, timedelta
import requests
import json

app = FastAPI(title="ACEITAÊ API", version="3.0.0")

# ==================================================
# CORS - Configuração completa
# ==================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://www.aceitae.com",
        "https://aceitae.com",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ==================================================
# VARIÁVEIS DE AMBIENTE (ASAAS)
# ==================================================
ASAAS_ENV = os.getenv("ASAAS_ENV", "sandbox")
ASAAS_API_KEY_SANDBOX = os.getenv("ASAAS_API_KEY_sandbox")
ASAAS_API_KEY_PROD = os.getenv("ASAAS_API_KEY_prod")

if ASAAS_ENV == "production":
    ASAAS_API_KEY = ASAAS_API_KEY_PROD
    ASAAS_URL = "https://www.asaas.com/api/v3"
else:
    ASAAS_API_KEY = ASAAS_API_KEY_SANDBOX
    ASAAS_URL = "https://sandbox.asaas.com/api/v3"

print(f"🔐 Ambiente ASAAS: {ASAAS_ENV}")
print(f"🔑 Chave ASAAS: {ASAAS_API_KEY[:10]}..." if ASAAS_API_KEY else "❌ Chave não encontrada!")

ASAAS_HEADERS = {
    "access_token": ASAAS_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

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
    cores: Optional[list] = []
    tamanhos: Optional[list] = []
    numeros: Optional[list] = []
    condicao: Optional[str] = "usado"
    quantidade: Optional[int] = 1
    peso: Optional[float] = 0.5
    altura: Optional[float] = 10
    largura: Optional[float] = 15
    comprimento: Optional[float] = 20

class Oferta(BaseModel):
    produto_id: int
    valor: float

# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================
def gerar_token(user_id: int, email: str):
    token_data = f"{user_id}:{email}:{time.time()}"
    return hashlib.sha256(token_data.encode()).hexdigest()

def gerar_link_whatsapp(telefone: str, mensagem: str):
    numero = re.sub(r'\D', '', telefone)
    if not numero.startswith('55'):
        numero = '55' + numero
    if len(numero) == 12:
        numero = numero[:4] + '9' + numero[4:]
    mensagem_codificada = quote(mensagem)
    return f"https://wa.me/{numero}?text={mensagem_codificada}"

def gerar_mensagem_oferta(produto_nome: str, valor_ofertado: float, comprador_nome: str, valor_pretendido: float):
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
https://aceitae.com/vendedor.html

⚠️ Oferta condicionada à sua aceitação. Você tem 48h para decidir."""
    return mensagem

# ==================================================
# FUNÇÕES ASAAS
# ==================================================
def criar_cliente_asaas(nome, email, cpf_cnpj, telefone=None):
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
# ROTAS DE USUÁRIO
# ==================================================
@app.post("/cadastrar")
def cadastrar(user: Usuario):
    existing = supabase.table("usuarios").select("*").eq("email", user.email).execute()
    if existing.data:
        raise HTTPException(400, "E-mail já cadastrado")
    
    usuario_data = {
        "nome": user.nome,
        "email": user.email,
        "telefone": user.telefone,
        "tipo": user.tipo,
        "senha": user.senha,
        "cpf": user.cpf,
        "pix": user.pix,
        "endereco": user.endereco,
        "whatsapp": user.whatsapp,
        "criado_em": datetime.now().isoformat()
    }
    
    result = supabase.table("usuarios").insert(usuario_data).execute()
    
    if user.tipo in ['vendedor', 'ambos'] and user.cpf:
        asaas_cliente = criar_cliente_asaas(user.nome, user.email, user.cpf, user.telefone)
        if asaas_cliente:
            supabase.table("usuarios").update({
                "asaas_customer_id": asaas_cliente.get("id")
            }).eq("email", user.email).execute()
    
    return {"mensagem": "Cadastro realizado com sucesso!"}

@app.post("/login")
def login(credenciais: LoginData):
    result = supabase.table("usuarios").select("*").eq("email", credenciais.email).eq("senha", credenciais.senha).execute()
    if not result.data:
        raise HTTPException(401, "E-mail ou senha inválidos")
    user = result.data[0]
    
    access_token = gerar_token(user["id"], user["email"])
    
    return {
        "access_token": access_token,
        "usuario_id": user["id"],
        "nome": user["nome"],
        "tipo": user["tipo"],
        "email": user["email"]
    }

@app.get("/usuarios/{usuario_id}/is-admin")
def verificar_admin(usuario_id: int):
    try:
        result = supabase.table("usuarios").select("is_admin, tipo").eq("id", usuario_id).execute()
        if not result.data:
            return {"is_admin": False}
        user = result.data[0]
        is_admin = user.get("is_admin", False) or user.get("tipo") == "admin"
        return {"is_admin": is_admin}
    except Exception as e:
        return {"is_admin": False}

# ==================================================
# ROTAS DE PRODUTO
# ==================================================
@app.post("/produtos")
def criar_produto(produto: Produto, vendedor_id: int):
    try:
        vendedor = supabase.table("usuarios").select("*").eq("id", vendedor_id).execute()
        if not vendedor.data:
            raise HTTPException(404, "Vendedor não encontrado")
        
        if vendedor.data[0]["tipo"] not in ["vendedor", "ambos"]:
            raise HTTPException(403, "Usuário não tem permissão para anunciar")
        
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
            "video": produto.video or "",
            "cores": produto.cores or [],
            "tamanhos": produto.tamanhos or [],
            "numeros": produto.numeros or [],
            "condicao": produto.condicao or "usado",
            "quantidade": produto.quantidade or 1,
            "peso": produto.peso or 0.5,
            "altura": produto.altura or 10,
            "largura": produto.largura or 15,
            "comprimento": produto.comprimento or 20,
            "criado_em": datetime.now().isoformat()
        }
        
        print(f"📦 Inserindo produto: {novo_produto['nome']} - Vendedor: {vendedor_id}")
        
        result = supabase.table("produtos").insert(novo_produto).execute()
        
        return {
            "produto_id": result.data[0]["id"],
            "mensagem": "Produto cadastrado! Aguardando vistoria."
        }
    except Exception as e:
        print(f"❌ Erro ao criar produto: {str(e)}")
        raise HTTPException(500, f"Erro interno: {str(e)}")

@app.get("/produtos")
def listar_produtos(status: Optional[str] = None, vendedor_id: Optional[int] = None):
    query = supabase.table("produtos").select("*")
    if status:
        query = query.eq("status", status)
    if vendedor_id:
        query = query.eq("vendedor_id", vendedor_id)
    result = query.execute()
    return {"produtos": result.data}

@app.put("/produtos/{produto_id}")
def atualizar_produto(produto_id: int, produto_atualizado: dict):
    produto_existente = supabase.table("produtos").select("*").eq("id", produto_id).execute()
    if not produto_existente.data:
        raise HTTPException(404, "Produto não encontrado")
    
    dados_atualizados = {
        "nome": produto_atualizado.get("nome"),
        "descricao": produto_atualizado.get("descricao"),
        "valor_pretendido": produto_atualizado.get("valor_pretendido"),
        "condicao": produto_atualizado.get("condicao"),
        "quantidade": produto_atualizado.get("quantidade"),
        "fotos": produto_atualizado.get("fotos"),
        "cores": produto_atualizado.get("cores"),
        "tamanhos": produto_atualizado.get("tamanhos"),
        "numeros": produto_atualizado.get("numeros"),
        "valor_exposicao": produto_atualizado.get("valor_pretendido", 0) * 1.10
    }
    dados_atualizados = {k: v for k, v in dados_atualizados.items() if v is not None}
    
    result = supabase.table("produtos").update(dados_atualizados).eq("id", produto_id).execute()
    return {"mensagem": "Produto atualizado com sucesso!", "produto": result.data[0]}

@app.delete("/produtos/{produto_id}")
def excluir_produto(produto_id: int):
    produto_existente = supabase.table("produtos").select("*").eq("id", produto_id).execute()
    if not produto_existente.data:
        raise HTTPException(404, "Produto não encontrado")
    
    supabase.table("ofertas").delete().eq("produto_id", produto_id).execute()
    supabase.table("produtos").delete().eq("id", produto_id).execute()
    return {"mensagem": "Produto excluído com sucesso!"}

# ==================================================
# FUNÇÃO AUXILIAR: GERAR PAGAMENTO AUTOMÁTICO
# ==================================================
def gerar_pagamento_automatico(comprador_id, produto_id, valor, oferta_id):
    """Gera pagamento PIX automaticamente para venda automática"""
    try:
        comprador = supabase.table("usuarios").select("*").eq("id", comprador_id).execute()
        if not comprador.data or not comprador.data[0].get("cpf"):
            return None
        
        comprador = comprador.data[0]
        
        produto = supabase.table("produtos").select("nome").eq("id", produto_id).execute()
        if not produto.data:
            return None
        produto = produto.data[0]
        
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
                }).eq("id", comprador_id).execute()
            else:
                return None
        
        data_vencimento = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        descricao = f"ACEITAÊ - {produto['nome']}"
        cobranca = criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento)
        
        if not cobranca or not cobranca.get("id"):
            return None
        
        link_pagamento = f"https://aceitae.com/pagamento.html?oferta={oferta_id}"
        
        supabase.table("ofertas").update({
            "asaas_payment_id": cobranca.get("id"),
            "asaas_pix_qr_code": cobranca.get("pixQrCode"),
            "asaas_pix_payload": cobranca.get("pixPayload"),
            "asaas_tipo_pagamento": "pix",
            "link_pagamento": link_pagamento,
            "status": "aguardando_pagamento"
        }).eq("id", oferta_id).execute()
        
        return link_pagamento
        
    except Exception as e:
        print(f"❌ Erro ao gerar pagamento automático: {e}")
        return None

# ==================================================
# ROTAS DE OFERTA
# ==================================================
@app.post("/ofertas")
def fazer_oferta(oferta: Oferta, comprador_id: int, comprador_nome: str):
    produto = supabase.table("produtos").select("*").eq("id", oferta.produto_id).execute()
    if not produto.data:
        raise HTTPException(404, "Produto não encontrado")
    
    produto = produto.data[0]
    
    if produto["status"] != "aprovado":
        raise HTTPException(400, "Produto não está disponível para ofertas")
    
    valor_pretendido = produto["valor_pretendido"]
    valor_oferta = oferta.valor
    
    oferta_existente = supabase.table("ofertas").select("*")\
        .eq("produto_id", oferta.produto_id)\
        .eq("comprador_id", comprador_id)\
        .eq("status", "pendente").execute()
    
    if oferta_existente.data:
        raise HTTPException(400, "Você já tem uma oferta pendente para este produto")
    
    if valor_oferta >= valor_pretendido:
        status_oferta = "venda_automatica"
        supabase.table("produtos").update({"status": "vendido"}).eq("id", oferta.produto_id).execute()
        mensagem = f"✅ Venda automática! Produto vendido por R$ {valor_oferta:.2f}"
    else:
        status_oferta = "pendente"
        mensagem = f"🟡 Oferta condicional enviada! Aguardando vendedor decidir"
    
    nova_oferta = {
        "produto_id": oferta.produto_id,
        "comprador_id": comprador_id,
        "comprador_nome": comprador_nome,
        "vendedor_id": produto["vendedor_id"],
        "valor": valor_oferta,
        "status": status_oferta,
        "condicional": valor_oferta < valor_pretendido,
        "valor_pretendido": valor_pretendido,
        "criado_em": datetime.now().isoformat()
    }
    
    result = supabase.table("ofertas").insert(nova_oferta).execute()
    oferta_id = result.data[0]["id"]
    
    link_pagamento = None
    if status_oferta == "venda_automatica":
        link_pagamento = gerar_pagamento_automatico(comprador_id, oferta.produto_id, valor_oferta, oferta_id)
        if link_pagamento:
            # Atualiza a oferta com o link
            supabase.table("ofertas").update({
                "link_pagamento": link_pagamento
            }).eq("id", oferta_id).execute()
            
            # Envia notificação para o comprador via WhatsApp
            comprador = supabase.table("usuarios").select("whatsapp").eq("id", comprador_id).execute()
            if comprador.data and comprador.data[0].get("whatsapp"):
                telefone = comprador.data[0]["whatsapp"]
                msg = f"🎉 Venda automática! Pague seu produto: {link_pagamento}"
                gerar_link_whatsapp(telefone, msg)
    
    link_whatsapp = None
    if status_oferta == "pendente":
        vendedor_info = supabase.table("usuarios").select("whatsapp, nome").eq("id", produto["vendedor_id"]).execute()
        if vendedor_info.data and vendedor_info.data[0].get("whatsapp"):
            telefone = vendedor_info.data[0]["whatsapp"]
            mensagem_whatsapp = gerar_mensagem_oferta(
                produto_nome=produto["nome"],
                valor_ofertado=valor_oferta,
                comprador_nome=comprador_nome,
                valor_pretendido=valor_pretendido
            )
            link_whatsapp = gerar_link_whatsapp(telefone, mensagem_whatsapp)
            print(f"🔗 Link WhatsApp: {link_whatsapp}")
    
    return {
        "mensagem": mensagem,
        "oferta_id": oferta_id,
        "status": status_oferta,
        "link_pagamento": link_pagamento,
        "notificationLink": link_whatsapp
    }

@app.get("/ofertas")
def listar_ofertas_comprador(comprador_id: int):
    result = supabase.table("ofertas").select("*").eq("comprador_id", comprador_id).execute()
    
    ofertas = []
    for oferta in result.data:
        produto = supabase.table("produtos").select("nome, vendedor_id").eq("id", oferta["produto_id"]).execute()
        vendedor_nome = "ACEITAÊ"
        if produto.data:
            vendedor = supabase.table("usuarios").select("nome").eq("id", produto.data[0]["vendedor_id"]).execute()
            if vendedor.data:
                vendedor_nome = vendedor.data[0]["nome"]
        
        ofertas.append({
            "id": oferta["id"],
            "produto_nome": produto.data[0]["nome"] if produto.data else "Produto",
            "vendedor_nome": vendedor_nome,
            "valor": oferta["valor"],
            "status": oferta["status"],
            "criado_em": oferta["criado_em"],
            "link_pagamento": oferta.get("link_pagamento")
        })
    
    return {"ofertas": ofertas}

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
        
        # Gera pagamento após vendedor aceitar
        link_pagamento = gerar_pagamento_automatico(
            oferta["comprador_id"], 
            oferta["produto_id"], 
            valor_oferta, 
            oferta_id
        )
        
        mensagem = f"🎉 ACEITAÊ! Venda confirmada!\nValor: R$ {valor_oferta:.2f}\nComissão (10%): R$ {comissao:.2f}\nVocê receberá: R$ {valor_liquido:.2f}"
        if link_pagamento:
            mensagem += f"\n🔗 Link para pagamento: {link_pagamento}"
        
        return {"mensagem": mensagem, "status": "aceita", "link_pagamento": link_pagamento}
    elif acao.upper() == "RECUSAR":
        supabase.table("ofertas").update({"status": "recusada"}).eq("id", oferta_id).execute()
        return {"mensagem": "❌ Oferta recusada", "status": "recusada"}
    else:
        raise HTTPException(400, "Ação inválida. Use 'ACEITAÊ' ou 'RECUSAR'")

@app.get("/ofertas/{oferta_id}")
def buscar_oferta(oferta_id: int):
    """Busca uma oferta específica pelo ID para a página de pagamento"""
    try:
        oferta = supabase.table("ofertas").select("*").eq("id", oferta_id).execute()
        if not oferta.data:
            raise HTTPException(404, "Oferta não encontrada")
        oferta = oferta.data[0]
        
        # Busca informações do produto
        produto = supabase.table("produtos").select("nome, vendedor_id, fotos").eq("id", oferta["produto_id"]).execute()
        produto_nome = produto.data[0]["nome"] if produto.data else "Produto"
        fotos = produto.data[0].get("fotos", []) if produto.data else []
        
        # Busca nome do vendedor
        vendedor_nome = "ACEITAÊ"
        if produto.data and produto.data[0].get("vendedor_id"):
            vendedor = supabase.table("usuarios").select("nome").eq("id", produto.data[0]["vendedor_id"]).execute()
            if vendedor.data:
                vendedor_nome = vendedor.data[0]["nome"]
        
        return {
            "id": oferta["id"],
            "produto_nome": produto_nome,
            "vendedor_nome": vendedor_nome,
            "valor": oferta["valor"],
            "status": oferta["status"],
            "quantidade": oferta.get("quantidade", 1),
            "foto": fotos[0] if fotos else "",
            "criado_em": oferta["criado_em"],
            "link_pagamento": oferta.get("link_pagamento"),
            "pix_payload": oferta.get("asaas_pix_payload"),
            "pix_qr_code": oferta.get("asaas_pix_qr_code"),
            "parcelas": oferta.get("asaas_parcelas", 1)
        }
    except Exception as e:
        print(f"❌ Erro ao buscar oferta: {str(e)}")
        raise HTTPException(500, str(e))


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
# ROTA: GERAR PAGAMENTO (PIX ou CARTÃO)
# ==================================================
@app.post("/ofertas/{oferta_id}/gerar-pagamento")
def gerar_pagamento_oferta(oferta_id: int, metodo: str = "pix", parcelas: int = 1):
    try:
        oferta = supabase.table("ofertas").select("*").eq("id", oferta_id).execute()
        if not oferta.data:
            raise HTTPException(404, "Oferta não encontrada")
        oferta = oferta.data[0]
        
        comprador = supabase.table("usuarios").select("*").eq("id", oferta["comprador_id"]).execute()
        if not comprador.data:
            raise HTTPException(404, "Comprador não encontrado")
        comprador = comprador.data[0]
        
        produto = supabase.table("produtos").select("*").eq("id", oferta["produto_id"]).execute()
        if not produto.data:
            raise HTTPException(404, "Produto não encontrado")
        produto = produto.data[0]
        
        if not comprador.get("cpf"):
            return {
                "erro": "comprador_sem_cpf",
                "mensagem": "O comprador precisa ter CPF cadastrado para gerar o pagamento."
            }
        
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
        link_pagamento = f"https://aceitae.com/pagamento.html?oferta={oferta_id}"
        
        if metodo.lower() == "pix":
            cobranca = criar_cobranca_pix_asaas(customer_id, valor, descricao, data_vencimento)
            if not cobranca or not cobranca.get("id"):
                return {"erro": "erro_cobranca", "mensagem": "Erro ao criar cobrança PIX no Asaas"}
            
            supabase.table("ofertas").update({
                "asaas_payment_id": cobranca.get("id"),
                "asaas_pix_qr_code": cobranca.get("pixQrCode"),
                "asaas_pix_payload": cobranca.get("pixPayload"),
                "asaas_tipo_pagamento": "pix",
                "link_pagamento": link_pagamento,
                "status": "aguardando_pagamento"
            }).eq("id", oferta_id).execute()
            
            return {
                "sucesso": True,
                "metodo": "pix",
                "mensagem": "Pagamento PIX gerado com sucesso!",
                "link_pagamento": link_pagamento,
                "pix_qr_code": cobranca.get("pixQrCode"),
                "pix_payload": cobranca.get("pixPayload"),
                "valor": valor,
                "vencimento": data_vencimento
            }
            
        elif metodo.lower() == "cartao":
            if parcelas < 1 or parcelas > 12:
                parcelas = 1
            
            cobranca = criar_cobranca_cartao_asaas(customer_id, valor, descricao, parcelas, data_vencimento)
            if not cobranca or not cobranca.get("id"):
                return {"erro": "erro_cobranca", "mensagem": "Erro ao criar cobrança com cartão no Asaas"}
            
            supabase.table("ofertas").update({
                "asaas_payment_id": cobranca.get("id"),
                "asaas_tipo_pagamento": "cartao",
                "asaas_parcelas": parcelas,
                "link_pagamento": link_pagamento,
                "status": "aguardando_pagamento"
            }).eq("id", oferta_id).execute()
            
            return {
                "sucesso": True,
                "metodo": "cartao",
                "mensagem": f"Pagamento com cartão gerado com sucesso! Parcelas: {parcelas}x",
                "link_pagamento": link_pagamento,
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
# WEBHOOK ASAAS
# ==================================================
@app.post("/webhook-asaas")
async def webhook_asaas(request: Request):
    try:
        data = await request.json()
        evento = data.get("event")
        payment_id = data.get("payment", {}).get("id")
        
        print(f"📩 Webhook recebido: {evento} - Payment ID: {payment_id}")
        
        if evento == "PAYMENT_CONFIRMED":
            oferta = supabase.table("ofertas").select("*").eq("asaas_payment_id", payment_id).execute()
            if oferta.data:
                supabase.table("ofertas").update({
                    "status": "pago",
                    "pago_em": datetime.now().isoformat()
                }).eq("id", oferta.data[0]["id"]).execute()
                
                print(f"✅ Pagamento confirmado para oferta {oferta.data[0]['id']}")
                return {"status": "ok", "message": "Pagamento confirmado"}
        
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return {"error": str(e)}

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
# ADMIN
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
