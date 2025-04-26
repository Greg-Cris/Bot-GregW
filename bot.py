import os
import discord
import aiohttp
import io 
from discord import ui, ButtonStyle
from discord.ext import commands
from discord import SelectOption
from dotenv import load_dotenv
import json
from discord.ui import Modal, TextInput
import logging



# Carregar variáveis de ambiente
dotenv_path = '.env'
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    raise FileNotFoundError(f"Arquivo .env não encontrado em: {dotenv_path}")

TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("Erro: TOKEN do Discord não foi carregado. Verifique o arquivo .env.")

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True  # Necessário para gerenciar categorias/canais
intents.members = True  # Necessário para gerenciar apelidos
bot = commands.Bot(command_prefix="!", intents=intents)

# IDs dos canais e cargos
RECRUTAMENTO_CHANNEL_ID = 1318264689666297916
CENTRAL_RECRUTADOR_CHANNEL_ID = 1318280171480158319
LOGS_RECRUTADORES_CHANNEL_ID = 1318265162045722694
RECRUTADO_ROLE_ID = 1319027281015996508  # ID do cargo "Recrutado"
MAIAS_ROLE_ID = 1333436933501747241  # ID do cargo "Maia"
EXONERACAO_CHANNEL_ID = 1341093413701025842  # Substitua com o ID correto
PEDIR_PD_CHANNEL_ID = 1341093413701025842  # Substitua com o ID correto

# IDs das categorias
CATEGORIAS = {
    "Categoria 1": "1334258941638610985",
    "Categoria 2": "1334259023578398815",
    "Categoria 3": "1334517272286597142",
    "Categoria 4": "1334517299301978152",
    "Categoria 5": "1334517325948260352",
}

# Caminho para o arquivo de mensagem fixa
MENSAGEM_FIXA_PATH = "mensagem_fixa.json"



class RecrutamentoView(ui.View):
    # Botão "Seja Recrutado"
    @discord.ui.button(label="Seja Recrutado", style=ButtonStyle.primary)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecrutamentoForm(discord_id=interaction.user.id))

import json

# Caminho para o arquivo de dados, agora isolado por usuário
ARQUIVO_TEMPLATE = "dados_{user_id}.json"

class ExoneracaoModal(discord.ui.Modal):
    id_input = ui.TextInput(
        label="ID / Nome / ID Discord:",
        placeholder="IDs por espaço ou Nomes por vírgula",
        required=True
    )

    def __init__(self, exoneracao_view, campo="ID"):
        super().__init__(title=f"Inserir {campo} manualmente")
        self.exoneracao_view = exoneracao_view
        self.campo = campo

    async def on_submit(self, interaction: discord.Interaction):
        # 1) Parse dos valores
        if self.campo == "Nome":
            entradas = [v.strip() for v in self.id_input.value.split(",") if v.strip()]
        else:
            entradas = self.id_input.value.strip().split()

        print(f"[DEBUG] {self.campo}s digitados: {entradas}")

        # 2) Monta opções para cada menu a partir dos resultados
        nome_opts = []
        id_opts = []
        discord_opts = []
        novos_ids = []  # Vamos armazenar os IDs e nomes para o JSON

        for valor in entradas:
            encontrado = None
            if self.campo == "ID":
                encontrado = next((m for m in interaction.guild.members
                                  if m.display_name.endswith(f" | {valor}")), None)
            elif self.campo == "Nome":
                encontrado = next((m for m in interaction.guild.members
                                  if valor.lower() == m.display_name.split(" | ")[0].lower()), None)
            else:  # ID Discord
                encontrado = next((m for m in interaction.guild.members
                                  if str(m.id) == valor), None)

            if encontrado:
                nome, uid = (encontrado.display_name.split(" | ", 1) + ["DESCONHECIDO"])[:2]
                nome_opts.append(discord.SelectOption(label=nome, value=nome))
                id_opts.append(discord.SelectOption(label=uid, value=uid))
                discord_opts.append(discord.SelectOption(label=str(encontrado.id), value=str(encontrado.id)))
                print(f"[DEBUG] Encontrado → {nome} | {uid} ({encontrado.id})")
                
                # Adicionando ao armazenamento para salvar no JSON
                novos_ids.append({
                    "nome": nome,
                    "id_usuario": uid,
                    "id_discord": str(encontrado.id)
                })
            else:
                # mesmo não encontrado, colocamos uma opção para o usuário ver o que não achou
                label = f"NÃO ENCONTRADO: {valor}"
                nome_opts.append(discord.SelectOption(label=label, value=valor))
                id_opts.append(discord.SelectOption(label=label, value=valor))
                discord_opts.append(discord.SelectOption(label=label, value=valor))
                print(f"[DEBUG] Não encontrado → {valor}")

        # 3) Atualiza os selects da view
        view = self.exoneracao_view
        view.select_nome.options       = nome_opts
        view.select_id.options         = id_opts
        view.select_id_discord.options = discord_opts

        view.select_nome.placeholder       = "Selecione um NOME"
        view.select_id.placeholder         = "Selecione um ID"
        view.select_id_discord.placeholder = "Selecione um ID Discord"

        view.select_nome.disabled       = False
        view.select_id.disabled         = False
        view.select_id_discord.disabled = False

        # 4) Envia de volta a view atualizada
        await interaction.response.edit_message(
            content="✅ Dados carregados! Agora escolha em cada menu a opção que deseja usar:",
            view=view
        )

        # 5) Salva os dados no arquivo JSON específico do usuário
        self.salvar_dados_json(novos_ids, interaction.user.id)

    def salvar_dados_json(self, novos_ids, user_id):
        arquivo = ARQUIVO_TEMPLATE.format(user_id=user_id)
        try:
            if os.path.exists(arquivo):
                with open(arquivo, "r") as f:
                    dados = json.load(f)
            else:
                dados = []
            dados.extend(novos_ids)
            with open(arquivo, "w") as f:
                json.dump(dados, f, indent=4)
            print(f"[DEBUG] Dados salvos em {arquivo}.")
        except Exception as e:
            print(f"[ERROR] Erro ao salvar {arquivo}: {e}")


class ConfirmacaoPunicaoModal(discord.ui.Modal):
    def __init__(self, nomes, ids_usuarios, motivo, punicao, ids_discord, arquivo):
        super().__init__(title="Confirmação de Punição")
        
        self.nomes = nomes
        self.ids_usuarios = ids_usuarios
        self.motivo = motivo
        self.punicao = punicao
        self.ids_discord = ids_discord
        self.arquivo = arquivo  # <- Agora ele existe


        self.nomes_input = TextInput(label="Nomes", default=", ".join(self.nomes), placeholder="Nomes dos usuários")
        self.nomes_input.disabled = True
        self.add_item(self.nomes_input)

        self.ids_input = TextInput(label="IDs", default=", ".join(map(str, self.ids_usuarios)), placeholder="IDs dos usuários")
        self.ids_input.disabled = True
        self.add_item(self.ids_input)

        self.motivo_input = TextInput(label="Motivo", default=self.motivo, placeholder="Motivo da punição")
        self.motivo_input.disabled = True
        self.add_item(self.motivo_input)

        self.punicao_input = TextInput(label="Punição", default=self.punicao, placeholder="Selecione a punição")
        self.punicao_input.disabled = True
        self.add_item(self.punicao_input)

        self.ids_discord_input = TextInput(label="IDs Discord", default=", ".join(map(str, self.ids_discord)), placeholder="IDs Discord")
        self.ids_discord_input.disabled = True
        self.add_item(self.ids_discord_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print("[DEBUG] Iniciando o processo de punição.")

            motivo = self.motivo_input.value
            punicao = self.punicao_input.value
            raw_ids = [id.strip() for id in self.ids_discord_input.value.split(",")]

            # Só pega os que são inteiros válidos
            ids_discord = []
            for val in raw_ids:
                if val.isdigit():
                    ids_discord.append(int(val))
                else:
                    print(f"[AVISO] Ignorando valor inválido no campo de ID Discord: '{val}'")

            if not ids_discord:
                await interaction.response.send_message(
                    "❌ Nenhum ID válido foi informado. Cancele e tente novamente.",
                    ephemeral=True
                )
                return

            ids_encontrados = []
            ids_nao_encontrados = []
            pessoas_processadas = []

            for id_discord in ids_discord:
                try:
                    print(f"[DEBUG] Tentando buscar o membro com ID Discord: {id_discord}...")
                    membro = await interaction.guild.fetch_member(id_discord)

                    if membro:
                        ids_encontrados.append(id_discord)
                        pessoas_processadas.append({
                            "nome": membro.display_name,
                            "id": "SEM ID",
                            "id_discord": id_discord,
                            "membro": membro
                        })
                    else:
                        ids_nao_encontrados.append(id_discord)
                        pessoas_processadas.append({
                            "nome": "NÃO ENCONTRADO",
                            "id": "DESCONHECIDO",
                            "id_discord": id_discord,
                            "membro": None
                        })

                except discord.NotFound:
                    print(f"[ERROR] Membro com ID Discord {id_discord} não encontrado.")
                    ids_nao_encontrados.append(id_discord)
                    pessoas_processadas.append({
                        "nome": "NÃO ENCONTRADO",
                        "id": "DESCONHECIDO",
                        "id_discord": id_discord,
                        "membro": None
                    })

                except discord.HTTPException as e:
                    print(f"[ERROR] Erro HTTP ao buscar o membro: {e}")
                    await interaction.response.send_message(
                        f"❌ **Erro de conexão ao tentar buscar o membro com ID {id_discord}.**",
                        ephemeral=True
                    )
                    return

            for pessoa in pessoas_processadas:
                nome = pessoa["nome"]
                id_usuario = pessoa["id"]
                id_discord = pessoa["id_discord"]
                membro = pessoa.get("membro")

                if membro:
                    try:
                        await membro.send(f"Você foi punido por: {motivo}")
                        if punicao == "PD":
                            await membro.kick(reason=motivo)
                            print(f"[PUNIÇÃO] {nome} (ID: {id_usuario}, Discord: {id_discord}) recebeu **PD**. ✅")
                        elif punicao == "BANIMENTO":
                            await membro.ban(reason=motivo)
                            print(f"[PUNIÇÃO] {nome} (ID: {id_usuario}, Discord: {id_discord}) foi **banido**. ✅")
                    except Exception as e:
                        print(f"[ERRO] Erro ao punir {nome} ({id_discord}): {e}")
                else:
                    print(f"[IGNORADO] Valor informado '{id_usuario}' não corresponde a nenhum membro. Nenhuma punição aplicada.")


            # 🔥 Remove o arquivo JSON temporário após aplicar as punições
            try:
                os.remove(self.arquivo)
                print(f"[DEBUG] Arquivo {self.arquivo} removido com sucesso.")
            except Exception as e:
                print(f"[ERRO] Falha ao remover arquivo: {e}")

        except Exception as e:
            print(f"[ERRO GERAL] Erro inesperado ao aplicar punições: {e}")
            await interaction.response.send_message("❌ Erro ao aplicar punições.", ephemeral=True)
            return

        # Nenhuma mensagem no Discord — só no terminal
        await interaction.response.defer()  # <- evita erro do modal
        print("✅ Punições aplicadas com sucesso.")

    

class ExoneracaoSelect(ui.Select):
    def __init__(self, label, options, modal_type):
        select_options = [discord.SelectOption(label=opt) for opt in options]
        super().__init__(placeholder=f"Selecione {label}", options=select_options)
        self.label = label
        self.modal_type = modal_type

    async def callback(self, interaction: discord.Interaction):
        print(f"[DEBUG] Menu suspenso {self.label} acionado.")

        if self.label == "ID":
            await interaction.response.send_modal(ExoneracaoModal(self.view, "ID"))

        elif self.label == "Nome":
            await interaction.response.send_modal(ExoneracaoModal(self.view, "Nome"))

        elif self.label == "ID Discord":
            await interaction.response.send_modal(ExoneracaoModal(self.view, "ID Discord"))

        elif self.label == "MOTIVO":
            motivo = self.values[0] if self.values else None
            print(f"[DEBUG] motivo selecionado: {motivo}")
            await interaction.response.defer(ephemeral=True)

        elif self.label == "PUNIÇÃO":
            user_id = interaction.user.id
            arquivo = f"dados_{user_id}.json"

            try:
                with open(arquivo, "r") as f:
                    dados = json.load(f)

                if isinstance(dados, list):
                    nomes = [item.get("nome") for item in dados]
                    ids = [item.get("id_usuario") for item in dados]
                    ids_discord = [item.get("id_discord") for item in dados]
                else:
                    raise ValueError("Formato de dados inválido no arquivo JSON.")

                if not nomes or not ids or not ids_discord:
                    await interaction.response.send_message(
                        "❌ Nenhum dado encontrado para aplicar punição.",
                        ephemeral=True
                    )
                    return

                print("[DEBUG] motivo selecionado:", self.view.select_motivo.values)
                print("[DEBUG] punição selecionada:", self.view.select_punicao.values)

                motivo = self.view.select_motivo.values[0] if self.view.select_motivo.values else None
                punicao = self.view.select_punicao.values[0] if self.view.select_punicao.values else None

                if not motivo or not punicao:
                    await interaction.response.send_message(
                        "❌ Você precisa selecionar tanto o motivo quanto a punição.",
                        ephemeral=True
                    )
                    return

                modal = ConfirmacaoPunicaoModal(nomes, ids, motivo, punicao, ids_discord, arquivo)
                await interaction.response.send_modal(modal)

                self.view.clear_items()
                await interaction.delete_original_response()

            except FileNotFoundError:
                await interaction.response.send_message("❌ Arquivo de dados não encontrado.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erro ao carregar dados: {e}", ephemeral=True)









class ExoneracaoView(ui.View):
    def __init__(self):
        super().__init__()

        # Criando os menus suspensos com nomes genéricos para iniciar
        self.select_id = ExoneracaoSelect("ID", ["Inserir Manualmente"], "ID")
        self.select_id_discord = ExoneracaoSelect("ID Discord", ["Inserir Manualmente"], "ID Discord")
        self.select_nome = ExoneracaoSelect("Nome", ["Inserir Manualmente"], "Nome")
        self.select_motivo = ExoneracaoSelect(
            "MOTIVO", 
            [
                "META ATRASADA", 
                "MULTA ATRASADA", 
                "META ATRASADA + FORA DO DC", 
                "PEDIU PD", 
                "DESRESPEITO A HIERARQUIA", 
                "OUTROS"
            ], 
            "Motivo"
        )
        self.select_punicao = ExoneracaoSelect("PUNIÇÃO", ["PD", "BANIMENTO"], "Punicao")

        # Adicionando os menus à view
        self.add_item(self.select_id)
        self.add_item(self.select_id_discord)
        self.add_item(self.select_nome)
        self.add_item(self.select_motivo)
        self.add_item(self.select_punicao)

    async def update_fields(self, nome, id, id_discord, interaction):
        """ Atualiza os campos do menu suspenso com as informações do usuário encontrado """
        print(f"[DEBUG] Atualizando campos: {nome}, {id}, {id_discord}")  # Log para acompanhar a atualização

        try:
            # Atualiza as opções do select e o placeholder dos menus
            self.select_nome.placeholder = f"NOME: {nome}"  # Atualiza o placeholder para 'NOME: nome_do_usuario'
            self.select_id.placeholder = f"ID: {str(id)}"  # Atualiza o placeholder para 'ID: 12345'
            self.select_id_discord.placeholder = f"ID Discord: {str(id_discord)}"  # Atualiza o placeholder para 'ID Discord: 67890'

            # Atualiza as opções para o nome, ID e ID do Discord
            self.select_nome.options = [discord.SelectOption(label=nome, value=nome)]  # Atualiza as opções para o nome
            self.select_id.options = [discord.SelectOption(label=str(id), value=str(id))]
            self.select_id_discord.options = [discord.SelectOption(label=str(id_discord), value=str(id_discord))]  # Atualiza as opções para o ID Discord

            # Habilita os menus para interação
            self.select_nome.disabled = False  # Habilita o menu de nome
            self.select_id.disabled = False  # Habilita o menu de ID
            self.select_id_discord.disabled = False  # Habilita o menu de ID Discord
            
            # Atualiza a mensagem com a nova view
            await interaction.response.edit_message(content="Preencha os menus suspensos:", view=self)

        except Exception as e:
            print(f"[ERROR] Falha ao atualizar os menus suspensos: {e}")  # Log de erro ao atualizar os menus
            await interaction.response.send_message(f"❌ **Erro ao atualizar os menus suspensos: {e}**", ephemeral=True)

class ConfirmarButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Confirmar", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view = self.view  # Acessa a view onde os selects estão

        if not view.select_nome.values or not view.select_id_discord.values:
            await interaction.response.send_message(
                "❌ Você precisa selecionar pelo menos um **nome** e um **ID Discord**.",
                ephemeral=True
            )
            return

        nomes_selecionados = view.select_nome.values
        ids_selecionados = view.select_id.values
        ids_discord_selecionados = [int(v) for v in view.select_id_discord.values if v.isdigit()]

        motivo = "Exoneração administrativa"  # Pode tornar dinâmico depois
        punicao = "PD"

        modal = ConfirmacaoPunicaoModal(
            nomes=nomes_selecionados,
            ids_usuarios=ids_selecionados,
            motivo=motivo,
            punicao=punicao,
            ids_discord=ids_discord_selecionados
        )

        await interaction.response.send_modal(modal)





class ExoneracaoEPedirPD(ui.View):
    @discord.ui.button(label="Exoneração", style=ButtonStyle.danger)
    async def button_exoneracao(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[DEBUG] Botão de Exoneração clicado por {interaction.user}.")  # Log para o clique do botão
        
        # Criando o embed
        embed = discord.Embed(
        title="🟡 Preencher punição!",
        description=(
            "1️⃣ Clique no 'Menu de Opções'.\n"
            "2️⃣ Escolha a punição desejada."
        ),
         color=discord.Color.yellow()
    )


        
        # Adicionando uma imagem no canto, se necessário (substitua pela URL da imagem desejada)
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/1041432042270904331/1231015064991957082/maias.png")

        # Enviando a mensagem com embed e o menu suspenso
        await interaction.response.send_message(embed=embed, view=ExoneracaoView(), ephemeral=True)
        
    @discord.ui.button(label="Pedir PD", style=ButtonStyle.secondary)
    async def button_pedir_pd(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        print(f"[LOG] O usuário {interaction.user} clicou no botão de Pedir PD.")

async def update_message(channel, tipo, view):
    mensagens_salvas = {}

    # Verifique se o arquivo existe e se ele contém dados
    if os.path.exists(MENSAGEM_FIXA_PATH):
        with open(MENSAGEM_FIXA_PATH, "r") as f:
            try:
                # Carregar o arquivo
                mensagens_salvas = json.load(f)
                
                # Verifique se a mensagem já existe para este tipo
                if tipo in mensagens_salvas:
                    mensagem_fixa_id = mensagens_salvas[tipo]
                    print(f"💬 Mensagem salva encontrada para {tipo}, tentando editar.")
                    mensagem_fixa = await channel.fetch_message(mensagem_fixa_id)
                    await mensagem_fixa.edit(content=f"Clique no botão para preencher o formulário de {tipo}!", view=view)
                    print(f"📨 Mensagem de {tipo} atualizada.")
                    return
                else:
                    print(f"⚠️ Mensagem de {tipo} não encontrada, criando uma nova.")
            except (discord.NotFound, ValueError, KeyError) as e:
                print(f"⚠️ Erro ao carregar o arquivo de mensagens: {e}")

    # Envia uma nova mensagem se não encontrar a anterior
    try:
        print(f"🚀 Enviando nova mensagem para {tipo}.")
        mensagem_fixa = await channel.send(f"Clique no botão para preencher o formulário de {tipo}!", view=view)
        # Atualiza o arquivo com o ID da nova mensagem
        mensagens_salvas[tipo] = mensagem_fixa.id

        with open(MENSAGEM_FIXA_PATH, "w") as f:
            json.dump(mensagens_salvas, f)
            print(f"📂 Arquivo de mensagens atualizado: {mensagens_salvas}")
        
        print(f"📨 Nova mensagem de {tipo} enviada.")
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem no canal de {tipo}: {e}")

# Evento ao iniciar o bot
@bot.event
async def on_ready():
    print(f'✅ Bot online! Logado como {bot.user}')

    # Canal de recrutamento
    recrutamento_channel = bot.get_channel(RECRUTAMENTO_CHANNEL_ID)
    if not recrutamento_channel:
        print(f"⚠️ Canal com ID {RECRUTAMENTO_CHANNEL_ID} não encontrado.")
        return

    # Canal de Exoneração
    exonera_channel = bot.get_channel(EXONERACAO_CHANNEL_ID)
    if not exonera_channel:
        print(f"⚠️ Canal com ID {EXONERACAO_CHANNEL_ID} não encontrado.")
        return

    # Canal de Pedir PD
    pedir_pd_channel = bot.get_channel(PEDIR_PD_CHANNEL_ID)
    if not pedir_pd_channel:
        print(f"⚠️ Canal com ID {PEDIR_PD_CHANNEL_ID} não encontrado.")
        return
        
    # Atualizar ou enviar mensagem de recrutamento para o canal de recrutamento
    await update_message(recrutamento_channel, "Recrutamento", RecrutamentoView())  # Chamada para atualizar a mensagem

    # Atualizar mensagens no canal de exoneração e pedir PD
    await update_message(exonera_channel, "Exoneração", ExoneracaoEPedirPD())





# Formulário de Recrutamento

class RecrutamentoForm(ui.Modal, title="Formulário de Recrutamento"):
    player_name = ui.TextInput(label="Nome (Personagem)", placeholder="Digite o nome do jogador")
    player_id = ui.TextInput(label="ID (Personagem)", placeholder="Digite o ID do jogador")
    discord_id = ui.TextInput(label="ID DISCORD (NÃO MEXER)", placeholder="Exemplo: 123456789012345678")

    def __init__(self, discord_id: str, **kwargs):
        super().__init__(**kwargs)
        self.discord_id.default = discord_id
        self.discord_id.disabled = True  # Desabilitar o campo para que não possa ser editado

    async def on_submit(self, interaction: discord.Interaction):
        print("Formulário de recrutamento enviado")
        recrutador_channel = bot.get_channel(CENTRAL_RECRUTADOR_CHANNEL_ID)

        # Atribuir os cargos "Recrutado" e "Maia" ao usuário
        guild = interaction.guild
        role_recrutado = guild.get_role(RECRUTADO_ROLE_ID)
        role_maia = guild.get_role(MAIAS_ROLE_ID)

        if role_recrutado:
            try:
                await interaction.user.add_roles(role_recrutado)
                print(f"✅ Cargo 'Recrutado' atribuído a {interaction.user.name}")
            except discord.Forbidden:
                print(f"❌ Permissão negada para atribuir o cargo 'Recrutado' a {interaction.user.name}")
            except discord.HTTPException as e:
                print(f"❌ Erro ao atribuir o cargo 'Recrutado' a {interaction.user.name}: {e}")
        else:
            print(f"❌ Cargo 'Recrutado' não encontrado com ID {RECRUTADO_ROLE_ID}")
        if role_maia:
            try:
                await interaction.user.add_roles(role_maia)
                print(f"✅ Cargo 'Maia' atribuído a {interaction.user.name}")
            except discord.Forbidden:
                print(f"❌ Permissão negada para atribuir o cargo 'Maia' a {interaction.user.name}")
            except discord.HTTPException as e:
                print(f"❌ Erro ao atribuir o cargo 'Maia' a {interaction.user.name}: {e}")
        else:
            print(f"❌ Cargo 'Maia' não encontrado com ID {MAIAS_ROLE_ID}")

        # Alterar o apelido do usuário
        novo_apelido = f"{self.player_name.value} | {self.player_id.value}"
        try:
            await interaction.user.edit(nick=novo_apelido)
            print(f"✅ Apelido alterado para: {novo_apelido}")
        except discord.Forbidden:
            print(f"❌ Permissão negada para alterar o apelido de {interaction.user.name}")
        except discord.HTTPException as e:
            print(f"❌ Erro ao alterar o apelido de {interaction.user.name}: {e}")

        if recrutador_channel:
            embed = discord.Embed(title="Recrutamento realizado!", color=discord.Color.blue())
            embed.add_field(name="Recruta:", value=f"{interaction.user.mention} | {self.player_id.value}", inline=False)
            embed.add_field(name="Nome (Personagem):", value=f"```{self.player_name.value}```", inline=False)
            embed.add_field(name="ID (Personagem):", value=f"```{self.player_id.value}```", inline=False)
            embed.add_field(name="Discord Id:", value=f"```{self.discord_id.default}```", inline=False)
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1041432042270904331/1231015064991957082/maias.png")

            view = DecisaoView(self.player_id.value, self.player_name.value, self.discord_id.default, recrutador=interaction.user)

            try:
                await recrutador_channel.send(embed=embed, view=view)
                await interaction.response.defer()
            except Exception as e:
                print(f"❌ Erro ao enviar formulário: {e}")
        else:
            await interaction.response.send_message("❌ Canal Central-Recrutador não encontrado.", ephemeral=True)
            print("❌ Canal Central-Recrutador não encontrado.")

# View com botões Aceitar e Rejeitar
class DecisaoView(ui.View):
    def __init__(self, player_id: str, player_name: str, discord_id: str, recrutador: discord.member):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_name = player_name
        self.discord_id = discord_id
        self.recrutador = recrutador

    def disable_all_buttons(self):
        """Desativa todos os botões da view."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @ui.button(label="Aceitar", style=ButtonStyle.success)
    async def aceitar_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        print("Botão 'Aceitar' clicado")

        # Desativar os botões antes de editar a mensagem
        self.disable_all_buttons()
        await interaction.message.edit(view=self)

        # Exibir a seleção de categoria
        await interaction.response.send_message(
            "Selecione uma categoria para criar o canal:",
            view=CategoriaView(self.player_id, self.player_name, self.discord_id, recrutador=interaction.user)
        )

    @ui.button(label="Rejeitar", style=ButtonStyle.danger)
    async def recusar_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        print("Botão 'Rejeitar' clicado")

        # Desativar os botões antes de editar a mensagem
        self.disable_all_buttons()
        await interaction.message.edit(view=self)

        # Apagar a mensagem original
        await interaction.message.delete()
        await interaction.response.defer()

class CategoriaView(ui.View):
    def __init__(self, player_id: str, player_name: str, discord_id: str, recrutador: discord.member):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_name = player_name
        self.discord_id = discord_id
        self.recrutador = recrutador

    @ui.select(
        placeholder="Escolha uma categoria",
        options=[discord.SelectOption(label=name, value=id) for name, id in CATEGORIAS.items()]
    )
    async def select_callback(self, interaction: discord.Interaction, select: ui.Select):
        categoria_id = int(select.values[0])  # ID da categoria selecionada
        guild = interaction.guild

        categoria = discord.utils.get(guild.categories, id=categoria_id)

        if categoria:
            # Verificar se a categoria já tem 50 canais
            if len(categoria.channels) >= 50:
                numero_categoria = 6  # Começa em "Recrutamento 6"
                nova_categoria = None

                # Procurar a próxima categoria disponível
                while not nova_categoria:
                    nome_nova_categoria = f"Recrutamento {numero_categoria}"
                    existente = discord.utils.get(guild.categories, name=nome_nova_categoria)

                    if existente:
                        if len(existente.channels) < 50:
                            nova_categoria = existente
                        else:
                            numero_categoria += 1  # Se estiver cheia, tenta a próxima
                    else:
                        nova_categoria = await guild.create_category(nome_nova_categoria)
                        print(f"✅ Nova categoria criada: {nome_nova_categoria}")

                categoria = nova_categoria  # Define a nova categoria como destino

            # Criar o canal dentro da categoria selecionada ou nova categoria
            channel = await guild.create_text_channel(f"⚪㇁-{self.player_name}-{self.player_id}", category=categoria)
            await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
            print(f"✅ Canal criado: {channel.name} (ID: {channel.id}) na categoria {categoria.name}")

            # 🔴 APAGAR A MENSAGEM APÓS A SELEÇÃO
            await interaction.message.delete()



            # 📌 Criar Embed principal (Informações do recrutado)
            embed_principal = discord.Embed(
               title="Informação",
               color=discord.Color.blue()
            )

            # Adicionar informações do recrutado
            embed_principal.add_field(name=" Nome", value=f"```{self.player_name}```", inline=True)
            embed_principal.add_field(name="", value=f"", inline=True)
            embed_principal.add_field(name="", value=f"", inline=True)

            embed_principal.add_field(name=" ID", value=f"```{self.player_id}```", inline=True)
            embed_principal.add_field(name=" Discord ID", value=f"```{self.discord_id}```", inline=False)

            # Adicionar um thumbnail (imagem pequena no embed)
            embed_principal.set_thumbnail(url="https://media.discordapp.net/attachments/1041432042270904331/1231015064991957082/maias.png")

            



            embed_metas = discord.Embed(
               title=" **Metas a Cumprir**",
               color=discord.Color.blue()
            )

            # Adicionar informações do recrutado
            embed_metas.add_field(name=" Diaria", value=f"```Meta 100 caixa de desmanche por dia na primeira semana.```", inline=True)
            embed_metas.add_field(name="", value=f"", inline=True)
            embed_metas.add_field(name=" Mensal", value=f"```Totalizando 500 Caixa desmanche ( segunda a sexta).```", inline=False)

            embed_metas.add_field(
               name=" **Dúvidas?**",
               value="Caso tenha dúvidas sobre como proceder, acesse a aba:\n"
                     "🔗 [Canal no Discord](https://discord.com/channels/1201744213893726208/1309213524580503602)\n"
                     "Ou procure um superior (Gerentes ou superiores).",
               inline=False
            )


            # ... código anterior ...

            # Enviar a mensagem no canal criado com os dois embeds
            await channel.send(embeds=[embed_principal])

            # Enviar o GIF animado
            gif_url = "https://www.imagensanimadas.com/data/media/562/linha-imagem-animada-0430.gif"
            await channel.send(gif_url)

            # Enviar a segunda mensagem com o embed
            await channel.send(embeds=[embed_metas])

            # ... código posterior ...


            # Log de recrutamento no canal de logs
            log_channel = bot.get_channel(LOGS_RECRUTADORES_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="Recrutamento realizado!",
                    color=discord.Color.green()
                )
                log_embed.add_field(name="Recrutador:", value=interaction.user.mention, inline=False)
                log_embed.add_field(name="Membro recrutado:", value=f"<@{self.discord_id}>", inline=False)

                log_view = ui.View()
                button = ui.Button(label="Por verificar!", style=ButtonStyle.success)

                async def button_callback(interaction: discord.Interaction):
                    button.label = "Verificado!"
                    button.style = ButtonStyle.secondary
                    button.disabled = True
                    await interaction.response.edit_message(view=log_view)
                
                button.callback = button_callback
                log_view.add_item(button)

                await log_channel.send(embed=log_embed, view=log_view)
            else:
                print(":x: Canal de logs não encontrado.")
        else:
            await interaction.response.send_message(":x: Categoria não encontrada.", ephemeral=True)

# Rodar o bot
try:
    bot.run(TOKEN)
except discord.LoginFailure:
    print("❌ TOKEN inválido! Verifique se o TOKEN no .env está correto.")
except Exception as e:
    print(f"❌ Ocorreu um erro ao rodar o bot: {e}")
