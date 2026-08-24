# 🎯 VagaJuniorFinder — Automação de Pesquisa Diária de Vagas (AI, Data Science & Tech)

**VagaJuniorFinder** é uma aplicação Python modular, inteligente e pronta para produção desenhada especificamente para automatizar a pesquisa diária de oportunidades de emprego de nível **Junior / Estágio IEFP** nas áreas de **Inteligência Artificial, Machine Learning, Engenharia de Dados e Software**.

O sistema recolhe vagas de 13 fontes distintas, aplica um filtro heurístico rigoroso para eliminar falsos juniores e vagas sénior, avalia a aderência técnica com Inteligência Artificial (Groq / Gemini) e sincroniza automaticamente os resultados qualificados diretamente com uma base de dados no **Notion**.

---

## 🚀 Funcionalidades Principais

- **Ingestão Multi-Fonte (13 Portais Ativos)**:
  - 🇵🇹 **LinkedIn Jobs** (API Pública Guest)
  - 🇵🇹 **ITJobs.pt** (API Pública / Feed RSS)
  - 🇵🇹 **Carga de Trabalhos** (Scraping de Vagas Tech em Portugal)
  - 🇵🇹 **Net-Empregos** (Scraping de TI, Data, AI & Estágios IEFP)
  - 🇵🇹 **IEFP Online** (Portal Oficial de Ofertas e Estágios IEFP)
  - 🎓 **Euraxess / Ergas** (Bolsas de Investigação & P&D em IA/ML em Portugal)
  - 🇪🇺 / 🇵🇹 **Landing.jobs** (API Pública Otimizada)
  - 🌍 **Jobicy** (API de Vagas Remotas Data & AI)
  - 🌍 **Remotive.com** (API de Vagas Remotas)
  - ☕ **Jobspresso** (Feed RSS de Vagas Remotas Tech)
  - 🇪🇺 **Arbeitnow** (API de Vagas Tech Europa & Remoto)
  - 🌐 **RemoteOK** (API de Vagas Remotas em Data & AI)
- **Deduplicação Inteligente**: Algoritmo baseado em Hashing SHA-256 com normalização avançada de nomes de empresas e cargos (`seen_store.py`), evitando vagas repetidas entre portais ou em dias consecutivos.
- **Filtragem em Duas Fases (Two-Stage Evaluation)**:
  - **Fase 1 (Heurística Estrita)**: Descarte imediato de vagas Senior/Lead (5+ anos), PhD, microtarefas/crowdsourcing, stacks não-alvo (PHP, SAP, Mobile, Suporte) e restrições geográficas incompatíveis (LATAM, US-only).
  - **Fase 2 (IA Semântica em Lote)**: Avaliação semântica via **Groq LLM** ou **Google Gemini**, analisando a descrição completa da vaga em lotes para atribuir Match Score (0-100%), deteção real de senioridade e justificativa técnica detalhada.
- **Suporte Multi-Perfil**: Gestão de múltiplos candidatos através de ficheiros JSON modulares (`profiles/*.json`), permitindo pesquisas personalizadas por stacks, títulos e bases de dados do Notion distintas.
- **Sincronização com Notion**: Integração direta com a API do Notion para inserção automática das vagas com propriedades estruturadas (Score, Empresa, Cargo, Modalidade, Localização, Link, Análise IA e Tecnologias).
- **Automação sem Custos (GitHub Actions)**: Execução automática agendada 2x por dia (**08:00 e 20:00 UTC / 09:00 e 21:00 Portugal**) com persistência de cache na branch `data`.

---

## 🛠️ Estrutura do Projeto

```
VagaJuniorFinder/
├── config.py                 # Configuração global e carregador dinâmico de perfis
├── main.py                   # Entrypoint principal para execução de perfil individual
├── run_all.py                # Executor em lote que itera por todos os perfis em profiles/
├── scraper.py                # Shim de retrocompatibilidade para o pacote scrapers/
├── scrapers/                 # Pacote modular de scrapers (12 portais suportados)
│   ├── __init__.py           # Exportação canónica dos scrapers e modelos
│   ├── base.py               # Classe base BaseScraper, Job model e funções de normalização
│   ├── pipeline.py           # Ingestão concorrente paralela (JobIngestionPipeline)
│   ├── linkedin.py
│   ├── itjobs.py
│   ├── landingjobs.py
│   ├── remotive.py
│   ├── arbeitnow.py
│   ├── remoteok.py
│   ├── cargadetrabalhos.py
│   ├── jobicy.py
│   ├── netempregos.py
│   ├── jobspresso.py
│   ├── euraxess.py
│   └── iefp.py
├── matcher.py                # Motor de scoring heurístico e orquestração do filtro
├── ai_evaluator.py           # Avaliador semântico em lote (Groq / Gemini) com fallbacks
├── notion_store.py           # Integração com a Notion API (schema inspection & sync)
├── company_extractor.py      # Extrator resiliente de nomes reais de empresas
├── seen_store.py             # Armazenamento atómico e expiração de IDs já vistos (30 dias)
├── scheduler.py              # Agendador local contínuo
├── requirements.txt          # Dependências Python do projeto
├── .env.example              # Template de variáveis de ambiente
├── README.md                 # Documentação do projeto
├── profiles/                 # Perfis de candidatos em formato JSON
│   ├── diogo_ai.json
│   ├── rafael.json
│   └── tiago.json
├── scripts/                  # Scripts utilitários de manutenção e reavaliação Notion
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

Edita o `.env` com as tuas chaves de API:
```env
# Notion Database Integration
NOTION_TOKEN=secret_your_notion_integration_token_here
NOTION_DATABASE_ID=your_32_character_notion_database_id_here
ENABLE_NOTION_SYNC=true

# AI Providers
GROQ_API_KEY=gsk_your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
ENABLE_AI_EVALUATION=true

# Opcional
ITJOBS_API_KEY=
```

---

## ⚡ Como Executar

### 1. Interface Web Interativa (Streamlit) 🖥️
Lança a aplicação gráfica no browser com dashboard de vagas, editor de perfis, métricas de mercado e execução on-demand:
```bash
streamlit run app.py
```

### 2. Teste de Validação em Linha de Comandos (Modo `--dry-run`)
Executa a ingestão e avaliação sem enviar registos para o Notion (ideal para inspecionar os scores na consola):
```bash
python main.py --dry-run
```

### 2. Execução de um Perfil Específico
```bash
# Executa com o perfil ativo por omissão (diogo_ai)
python main.py

# Executa com outro perfil específico (ex: rafael)
$env:ACTIVE_PROFILE="rafael"; python main.py
```

### 3. Execução de Todos os Perfis (`run_all.py`)
Percorre sequencialmente todos os ficheiros dentro da pasta `profiles/`:
```bash
python run_all.py
```

### 4. Executar a Suite de Testes Automatizados
```bash
python -m unittest discover tests
```

---

## ⚙️ Automação Gratuita no GitHub Actions

O projeto já inclui o workflow `.github/workflows/daily_job_search.yml`. Para colocar a automação a correr na nuvem:

1. No teu repositório GitHub, acede a **Settings** > **Secrets and variables** > **Actions**.
2. Adiciona as seguintes **Repository Secrets**:
   - `NOTION_TOKEN`
   - `NOTION_DATABASE_ID`
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `ITJOBS_API_KEY` (opcional)
3. O GitHub Actions executará automaticamente a pesquisa todos os dias às **08:00 e 20:00 UTC (09:00 e 21:00 em Portugal Continental)**, sincronizando todas as novas vagas diretamente com o Notion e persistindo o histórico na branch `data`.

---

## 👤 Perfis Suportados
- **Diogo Oliveira**: Junior AI Engineer, Junior Data Scientist, Machine Learning Engineer, RAG/LLM Developer.
- **Rafael**: Junior Cybersecurity Analyst, Administrador de Sistemas & Redes Júnior, IT Support Specialist.
