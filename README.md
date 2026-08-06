# 🎯 VagaJuniorFinder — Automação de Pesquisa Diária de Vagas (AI & Data Science)

**VagaJuniorFinder** é uma aplicação Python modular, inteligente e pronta para produção desenhada especificamente para automatizar a pesquisa diária de oportunidades de emprego de nível **Junior / Estágio IEFP** nas áreas de **Inteligência Artificial, Machine Learning e Data Science**.

---

## 🚀 Funcionalidades

- **Ingestão Multi-Fonte (14 Portais)**:
  - 🇵🇹 **LinkedIn Jobs** (API Pública Guest)
  - 🇵🇹 **ITJobs.pt** (API Pública / Feed RSS)
  - 🇵🇹 **Carga de Trabalhos** (Scraping de Vagas Tech em Portugal)
  - 🇵🇹 **Net-Empregos** (Scraping de TI, Data, AI & Estágios IEFP)
  - 🇵🇹 **Teamlyzer Jobs** (Scraping de Ofertas Tech em Portugal)
  - 🎓 **Euraxess / Ergas** (Bolsas de Investigação & P&D em IA/ML em Portugal)
  - 🇪🇺 / 🇵🇹 **Landing.jobs** (API Pública)
  - 🌍 **Jobicy** (API de Vagas Remotas Data & AI)
  - 🏔️ **Himalayas** (API de Vagas Remotas Tech Globais)
  - 🌍 **Remotive.com** (API de Vagas Remotas)
  - ☕ **Jobspresso** (Feed RSS de Vagas Remotas Tech)
  - 🇪🇺 **Arbeitnow** (API de Vagas Tech Europa & Remoto)
  - 💻 **WeWorkRemotely** (Feed RSS de Vagas Remotas)
  - 🌐 **RemoteOK** (API de Vagas Remotas em Data & AI)
- **Deduplicação Inteligente**: Algoritmo baseado em Hashing SHA-256 para evitar vagas repetidas.
- **Match Score & Filtragem**: Pontuação de 0 a 100% calculada por sobreposição de stack (`Python`, `SQL`, `FastAPI`, `RAG`, `LangChain`, `Scikit-learn`, `DuckDB`, etc.), bonificação de títulos Junior/Estágio IEFP e eliminação automática de vagas Senior/Lead (5+ anos).
- **Relatórios Markdown**: Geração diária em `reports/job_report_YYYY-MM-DD.md` com estatísticas, vagas de destaque (≥80%), vagas promissoras (60-79%) e botões de candidatura rápida.
- **Dicas Personalizadas de CV**: Sugestões automáticas de adaptação de CV para destacar competências específicas requisitadas pela vaga.
- **Notificação por Telegram**: Envia resumos estilizados e relatórios em Markdown e Excel (.xlsx) para o Telegram.
- **Automação sem Custos**: Execução automática via **GitHub Actions** todos os dias às **21:00 (9 PM / 20:00 UTC)** ou agendador local em daemon.

---

## 🛠️ Estrutura do Projeto

```
VagaJuniorFinder/
├── config.py             # Perfil do candidato & configurações do sistema
├── scraper.py            # Módulo de Ingestão Multi-fonte & Deduplicação
├── matcher.py            # Módulo de Scoring, Filtragem & Recomendação de CV
├── report_builder.py     # Gerador de relatórios Markdown estilizados
├── telegram_notifier.py  # Notificador para Telegram (Mensagens HTML & Ficheiros)
├── main.py               # Entrypoint principal (CLI com suporte a --dry-run)
├── scheduler.py          # Agendador local contínuo
├── requirements.txt      # Dependências Python
├── .env.example          # Template de variáveis de ambiente
├── README.md             # Documentação do projeto
└── .github/
    └── workflows/
        └── daily_job_search.yml  # Automação no GitHub Actions (21:00 / 20:00 UTC)
```

---

## 📦 Instalação e Configuração

### 1. Clonar / Aceder ao Diretório
```bash
cd VagaJuniorFinder
```

### 2. Criar e Ativar Ambiente Virtual Python
```bash
python -m venv venv

# No Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# No Linux/macOS:
source venv/bin/activate
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar Variáveis de Ambiente (`.env`)
Copia o ficheiro de exemplo `.env.example` para `.env`:
```bash
cp .env.example .env
```

Edita o ficheiro `.env` com as tuas credenciais do Telegram e chaves de API:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=123456789
GROQ_API_KEY=gsk_your_groq_api_key_here
```

---

## ⚡ Como Executar

### 1. Teste de Validação (Modo `--dry-run`)
Gera o relatório diário sem enviar notificações (ideal para testar a raspagem e ver os resultados):
```bash
python main.py --dry-run
```

O relatório em Markdown será gravado em `reports/job_report_YYYY-MM-DD.md`.

### 2. Execução Completa
```bash
python main.py
```

### 3. Agendador Local Contínuo
Para manter o script a rodar em background no teu computador localmente todos os dias às 21:00:
```bash
python scheduler.py
```

---

## ⚙️ Automação Gratuita no GitHub Actions

O projeto já inclui o workflow `.github/workflows/daily_job_search.yml`. Para colocar a automação a rodar na nuvem sem custos:

1. Cria um repositório no GitHub e envia este código (`git push origin main`).
2. No repositório do GitHub, vai a **Settings** > **Secrets and variables** > **Actions**.
3. Adiciona as tuas **Repository Secrets** (ex: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GROQ_API_KEY`, etc.).
4. O GitHub Actions executará a pesquisa todos os dias às **21:00 (20:00 UTC)** e enviará as notificações automaticamente. Podes também disparar a pesquisa manualmente no separador **Actions** > **Run workflow**.

---

## 👨‍💻 Desenvolvido para
- **Candidato**: Diogo Oliveira
- **Formação**: Licenciatura em Engenharia Informática (Média 15/20)
- **Elegibilidade**: Estágio Profissional IEFP / ATIVAR.pt
- **Perfil Target**: Junior AI Engineer, Junior Data Scientist, Machine Learning Engineer, RAG / NLP Developer.
