# 🎯 VagaJuniorFinder — Automação de Pesquisa Diária de Vagas (AI, Data Science & Tech)

**VagaJuniorFinder** é uma aplicação Python modular, inteligente e pronta para produção desenhada especificamente para automatizar a pesquisa diária de oportunidades de emprego de nível **Junior / Estágio IEFP** nas áreas de **Inteligência Artificial, Machine Learning, Engenharia de Dados, Cibersegurança e Engenharia de Software**.

O sistema recolhe em simultâneo mais de **2.300 ofertas de 15 fontes distintas**, aplica um filtro heurístico rigoroso para eliminar falsos juniores e vagas sénior, avalia a aderência técnica com Inteligência Artificial (Groq / Google Gemini) e sincroniza automaticamente os resultados qualificados diretamente com uma base de dados no **Notion**.

---

## 🚀 Funcionalidades Principais

- **Ingestão Multi-Fonte Massiva (15 Portais Ativos em Simultâneo)**:
  - 🇵🇹 **LinkedIn Jobs**: Extração pública com paginação contínua e raspagem do corpo completo da oferta.
  - 🇵🇹 **Net-Empregos**: Ingestão via Feed RSS oficial com **1.000 ofertas em tempo real** combinada com pesquisa concorrente com normalização de acentos.
  - 🇵🇹 **Indeed Portugal**: Extração direta resiliente com impersonação TLS Chrome (`curl_cffi`).
  - 🇵🇹 **ITJobs.pt**: Integração direta com a API Pública Oficial e RSS Feeds em Portugal.
  - 🇵🇹 **Teamlyzer**: Curadoria 100% tech em Portugal com avaliações, salários médios e links diretos de candidatura.
  - 🇵🇹 **IEFP Online**: Ingestão do portal público oficial de empregos e estágios profissionais **ATIVAR.pt**.
  - 🇵🇹 **Sapo Emprego**: Scraping estruturado do componente Vue com metadados de ofertas IT.
  - 🇵🇹 **Carga de Trabalhos**: Raspagem concorrente de vagas tech, dados e web em Portugal.
  - 🎓 **Euraxess / Ergas**: Bolsas de investigação científica e projetos de I&D em IA, ML e Computação em universidades portuguesas.
  - 🇪🇺 / 🇵🇹 **Landing.jobs**: API REST v1 oficial + Feeds Atom + Edge Relay Proxy para contorno transparente de Cloudflare.
  - 🇪🇺 **Arbeitnow**: API de vagas tech na Europa, Portugal e regime 100% Remoto.
  - 🌐 **RemoteOK**: API global de vagas remotas em Data Science, AI e Backend.
  - 🌍 **Jobicy**: Ingestão de vagas remotas globais em Engenharia e Inteligência Artificial.
  - 🌍 **Remotive.com**: API categorizada de ofertas tech globais e europeias.
  - ☕ **Jobspresso**: Feed RSS estruturado de vagas tech e dados com suporte a trabalho remoto.

- **Arquitetura Resiliente Anti-Bloqueio (WAF/Cloudflare)**:
  - Motor `safe_fetch` baseado em `curl_cffi` com TLS Fingerprint Impersonation (Chrome 120).
  - Seguidor automático de redirecionamentos HTTP (`allow_redirects=True`).
  - Edge Proxy Relay para contorno de bloqueios de IP de datacenters no GitHub Actions.

- **Deduplicação Inteligente em Duas Fases**:
  - Hashing SHA-256 sobre chaves canónicas normalizadas de `cargo__empresa` (`seen_store.py`), evitando processamento duplicado entre portais e em dias consecutivos.
  - Verificação prévia na base de dados do Notion para evitar inserções redundantes.

- **Filtragem e Scoring em Duas Fases (Two-Stage Evaluation)**:
  - **Fase 1 (Heurística Estrita)**: Descarte instantâneo de vagas Senior/Lead (3-5+ anos), PhD, microtarefas de crowdsourcing/anotação, stacks não-alvo (PHP legado, SAP, Cobol) e restrições geográficas incompatíveis (LATAM/US-only).
  - **Fase 2 (IA Semântica em Lote)**: Avaliação semântica via **Groq LLM** (`openai/gpt-oss-120b`, `llama-3.3-70b`) ou **Google Gemini** (`gemini-3.5-flash-lite`, `gemini-2.5-flash`), gerando Match Score (0-100%), deteção real de senioridade e justificativa técnica objetiva.

- **Suporte Multi-Perfil**:
  - Gestão de múltiplos candidatos através de ficheiros JSON modulares (`profiles/*.json`), permitindo pesquisas personalizadas por stacks, queries, títulos e bases de dados do Notion independentes.

- **Sincronização com Notion**:
  - Inserção automática das vagas com propriedades ricas: *Score*, *Empresa*, *Cargo*, *Modalidade*, *Localização*, *Link*, *Análise IA* e *Tecnologias Identificadas*.

- **Automação Contínua sem Custos (GitHub Actions)**:
  - Execução automática agendada 2x por dia (**08:00 e 20:00 UTC / 09:00 e 21:00 em Portugal Continental**) com persistência de cache na branch `data`.

---

## 🛠️ Estrutura do Projeto

```
VagaJuniorFinder/
├── config.py                 # Configuração global e carregador dinâmico de perfis
├── main.py                   # Entrypoint principal para execução de perfil individual
├── run_all.py                # Executor em lote que itera por todos os perfis em profiles/
├── scraper.py                # Shim de retrocompatibilidade para o pacote scrapers/
├── scrapers/                 # Pacote modular de scrapers (15 portais ativos)
│   ├── __init__.py           # Exportação canónica dos scrapers e modelos
│   ├── base.py               # Classe base BaseScraper, Job model, safe_fetch e normalização
│   ├── pipeline.py           # Ingestão paralela multithread (JobIngestionPipeline)
│   ├── linkedin.py           # LinkedIn Guest API
│   ├── indeed.py             # Indeed Portugal Scraper
│   ├── netempregos.py        # Net-Empregos (RSS 1000 + Pesquisa)
│   ├── itjobs.py             # ITJobs.pt API / RSS
│   ├── teamlyzer.py          # Teamlyzer Tech Portugal
│   ├── landingjobs.py        # Landing.jobs REST API + Edge Relay
│   ├── sapo.py               # Sapo Emprego Scraper
│   ├── iefp.py               # IEFP Online & Estágios ATIVAR.pt
│   ├── cargadetrabalhos.py   # Carga de Trabalhos Portugal
│   ├── euraxess.py           # Euraxess / Bolsas de Investigação
│   ├── arbeitnow.py          # Arbeitnow Europe & Remote
│   ├── remoteok.py           # RemoteOK Global Remote
│   ├── jobicy.py             # Jobicy Remote API
│   ├── remotive.py           # Remotive Tech Categories
│   └── jobspresso.py         # Jobspresso Remote RSS
├── matcher.py                # Motor de scoring heurístico e orquestração do filtro
├── ai_evaluator.py           # Avaliador semântico em lote (Groq / Gemini) com rotação resiliente
├── notion_store.py           # Integração com a Notion API (schema inspection & sync)
├── company_extractor.py      # Extrator resiliente de nomes reais de empresas
├── seen_store.py             # Armazenamento atómico e expiração de IDs já vistos (30 dias)
├── scheduler.py              # Agendador local contínuo
├── app.py                    # Dashboard interativo em Streamlit
├── requirements.txt          # Dependências Python do projeto
├── .env.example              # Template de variáveis de ambiente
├── README.md                 # Documentação do projeto
├── profiles/                 # Perfis de candidatos em formato JSON
│   ├── diogo.json            # Perfil: Diogo Oliveira (AI & Data)
│   ├── rafael.json           # Perfil: Rafael (Cibersegurança & Redes)
│   └── tiago.json            # Perfil: Tiago Alves (Software & Backend)
├── tests/                    # Suite de testes unitários automatizados (50 testes)
│   └── test_suite.py
└── .github/
    └── workflows/
        └── daily_job_search.yml  # Automação no GitHub Actions (08:00 e 20:00 UTC)
```

---

## 📦 Instalação e Configuração

### 1. Clonar o Repositório e Criar Ambiente Virtual
```bash
git clone https://github.com/Didass7/VagaJuniorFinder.git
cd VagaJuniorFinder

# Criar ambiente virtual
python -m venv venv

# Ativar no Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Ativar no Linux/macOS:
source venv/bin/activate
```

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente (`.env`)
Copia o ficheiro de exemplo `.env.example` para `.env`:
```bash
cp .env.example .env
```

Edita o `.env` com as tuas credenciais:
```env
# Notion Database Integration
NOTION_TOKEN=secret_your_notion_integration_token_here
NOTION_DATABASE_ID=your_32_character_notion_database_id_here
ENABLE_NOTION_SYNC=true

# Provedores de IA (Pelo menos um recomendado)
GROQ_API_KEY=gsk_your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
ENABLE_AI_EVALUATION=true

# Opcional (Chaves de API adicionais)
ITJOBS_API_KEY=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
JOOBLE_API_KEY=
```

---

## ⚡ Como Executar

### 1. Dashboard Gráfico Interativo (Streamlit) 🖥️
Lança a interface web para visualizar vagas ingeridas, métricas de mercado, editar perfis e disparar a pipeline on-demand:
```bash
streamlit run app.py
```

### 2. Teste de Validação em Linha de Comandos (Modo `--dry-run`)
Executa a ingestão e scoring heurístico/IA sem enviar alterações para o Notion:
```bash
python main.py --dry-run
```

### 3. Execução de um Perfil Específico
```bash
# Executa com o perfil ativo por omissão (diogo)
python main.py

# Executa com outro perfil específico (ex: rafael)
$env:ACTIVE_PROFILE="rafael"; python main.py
```

### 4. Execução de Todos os Perfis em Lote (`run_all.py`)
Percorre sequencialmente todos os perfis configurados na pasta `profiles/`:
```bash
python run_all.py
```

### 5. Executar a Suite de Testes Unitários
```bash
python -m unittest discover tests
```

---

## ⚙️ Automação no GitHub Actions

O projeto inclui o workflow [`.github/workflows/daily_job_search.yml`](.github/workflows/daily_job_search.yml). Para ativar a automação diária na nuvem:

1. No teu repositório GitHub, acede a **Settings** > **Secrets and variables** > **Actions**.
2. Adiciona as seguintes **Repository Secrets**:
   - `NOTION_TOKEN`
   - `NOTION_DATABASE_ID`
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `ITJOBS_API_KEY` (opcional)
3. O GitHub Actions executará automaticamente a pesquisa todos os dias às **07:17 e 19:17 UTC (08:17 e 20:17 em Portugal Continental no Verão)**, sincronizando todas as novas vagas diretamente com o Notion e persistindo o histórico na branch `data`.

---

## 👤 Perfis Suportados
- **Diogo Oliveira** (`diogo.json`): Junior AI Engineer, Junior Data Scientist, Machine Learning Engineer, RAG/LLM Developer, Python Backend.
- **Rafael** (`rafael.json`): Junior Cybersecurity Analyst, Administrador de Sistemas & Redes Júnior, SOC Analyst, IT Support Specialist.
- **Tiago Alves** (`tiago.json`): Junior Software Engineer, Full Stack Developer, Junior Backend Developer.
