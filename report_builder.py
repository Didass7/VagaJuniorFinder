import datetime
import os
from typing import List, Dict
from collections import Counter
from config import CandidateProfile
from matcher import ScoredJob

class ReportBuilder:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def build_markdown(self, scored_jobs: List[ScoredJob]) -> str:
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        
        top_matches = [j for j in scored_jobs if j.score >= 80.0]
        promising_matches = [j for j in scored_jobs if 60.0 <= j.score < 80.0]
        other_matches = [j for j in scored_jobs if j.score < 60.0]

        md = []
        md.append(f"# 🎯 Relatório Diário de Vagas — AI & Data Science (Junior)")
        md.append(f"**Candidato:** {self.profile.name} | **Data:** {today_str}\n")
        
        # Stats summary badges
        md.append(f"### 📊 Estatísticas do Dia")
        md.append(f"- 🔎 **Total de Vagas Analisadas:** `{len(scored_jobs)}`")
        md.append(f"- 🔥 **Destaques (Match ≥ 80%):** `{len(top_matches)}`")
        md.append(f"- ⚡ **Promissoras (Match 60-79%):** `{len(promising_matches)}`")
        md.append(f"- 📌 **Outras Vagas Relevantes:** `{len(other_matches)}`\n")
        md.append("---\n")

        # Top Matches Section
        md.append(f"## 🔥 Vagas Destaque (Match ≥ 80%)\n")
        if not top_matches:
            md.append("*Nenhuma vaga atingiu o threshold de ≥ 80% no dia de hoje. Consulta as vagas promissoras abaixo.*\n")
        else:
            for sj in top_matches:
                md.append(self._format_job_card(sj))

        md.append("---\n")

        # Promising Matches Section
        md.append(f"## ⚡ Outras Oportunidades Promissoras (Match 60-79%)\n")
        if not promising_matches:
            md.append("*Nenhuma vaga encontrada nesta categoria no dia de hoje.*\n")
        else:
            for sj in promising_matches:
                md.append(self._format_job_card(sj))

        md.append("---\n")

        # Other Relevant Opportunities Section (Top 5 of 45-59%)
        other_top5 = [j for j in other_matches if j.score >= 45.0][:5]
        if other_top5:
            md.append(f"## 📌 Outras Oportunidades Relevantes (Top 5 | Match 45-59%)\n")
            for sj in other_top5:
                md.append(self._format_job_card(sj))
            md.append("---\n")

        # Dynamic Tech Stack Demand Trends Section
        md.append(self._build_tech_trends_section(scored_jobs))

        md.append("---\n")
        md.append(f"*Relatório gerado automaticamente por VagaJuniorFinder a {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}.*")

        return "\n".join(md)

    def _format_job_card(self, sj: ScoredJob) -> str:
        job = sj.job
        lines = []
        
        # Title and Badges
        iefp_badge = " | `Elegível IEFP`" if job.iefp_mentioned else ""
        mode_badge = f"`{job.work_mode}`"
        lines.append(f"### 💼 [{job.title}]({job.link})")
        lines.append(f"**Empresa:** {job.company} &nbsp;|&nbsp; **Localização:** {job.location} &nbsp;|&nbsp; **Fonte:** `{job.source}`")
        lines.append(f"**Match Score:** `{sj.score}%` &nbsp;|&nbsp; {mode_badge} &nbsp;|&nbsp; **Nível:** `{sj.seniority_status}`{iefp_badge}\n")

        # Matched Skills
        if sj.matched_skills:
            skills_formatted = " ".join([f"`{s}`" for s in sj.matched_skills])
            lines.append(f"**Stack Exigida:** {skills_formatted}\n")

        # Clean Description Snippet
        clean_desc = job.description[:260].replace("\n", " ").strip() + "..."
        lines.append(f"> {clean_desc}\n")

        # Quick Apply Link
        lines.append(f"👉 [**🚀 Candidatar Rápidamente**]({job.link})\n")
        lines.append("---\n")
        return "\n".join(lines)

    def _build_tech_trends_section(self, scored_jobs: List[ScoredJob]) -> str:
        lines = ["## 📈 Tendências de Tecnologias Requisitadas Hoje\n"]
        
        skill_counts = Counter()
        for sj in scored_jobs:
            for skill in sj.matched_skills:
                skill_counts[skill] += 1
                
        if not skill_counts:
            lines.append("*Sem dados estatísticos de stack para hoje.*")
            return "\n".join(lines)
            
        lines.append("Distribuição das tecnologias mais procuradas nas vagas analisadas:\n")
        top_skills = skill_counts.most_common(10)
        
        for skill, count in top_skills:
            pct = round((count / len(scored_jobs)) * 100, 1)
            lines.append(f"- **{skill.title()}**: `{count} vagas` ({pct}%)")
            
        lines.append("")
        return "\n".join(lines)

    def save_report(self, markdown_content: str, output_dir: str = "reports") -> str:
        os.makedirs(output_dir, exist_ok=True)
        today_filename = f"job_report_{datetime.date.today().isoformat()}.md"
        filepath = os.path.join(output_dir, today_filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return filepath
