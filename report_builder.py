import datetime
import os
from typing import List, Dict
from config import CandidateProfile
from matcher import ScoredJob

class ReportBuilder:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def build_markdown(self, scored_jobs: List[ScoredJob]) -> str:
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        
        top_matches = [j for j in scored_jobs if j.score >= 75.0]
        promising_matches = [j for j in scored_jobs if 55.0 <= j.score < 75.0]

        total_recommended = len(top_matches) + len(promising_matches)

        md = []
        md.append(f"# Relatório Diário de Vagas — AI & Data Science (Junior / IEFP)")
        md.append(f"**Candidato:** {self.profile.name} &nbsp;|&nbsp; **Data:** {today_str}\n")
        
        # Summary Stats
        md.append(f"### Resumo")
        md.append(f"- **Total Recomendadas (≥55%):** `{total_recommended}` &nbsp;|&nbsp; **Destaques (≥75%):** `{len(top_matches)}` &nbsp;|&nbsp; **Promissoras (55-74%):** `{len(promising_matches)}`")
        md.append("\n---\n")

        # Top Matches Section
        md.append(f"## Vagas Destaque (Match ≥ 75%)\n")
        if not top_matches:
            md.append("*Nenhuma vaga atingiu a pontuação de destaque no dia de hoje (requisitos estritos de 0-1 ano de experiência e âmbito AI/Data).* \n")
        else:
            for sj in top_matches:
                md.append(self._format_job_card_md(sj))

        md.append("---\n")

        # Promising Matches Section
        md.append(f"## Oportunidades Promissoras (Match 55-74%)\n")
        if not promising_matches:
            md.append("*Nenhuma vaga encontrada nesta categoria no dia de hoje.*\n")
        else:
            for sj in promising_matches:
                md.append(self._format_job_card_md(sj))

        md.append("\n---\n")
        md.append(f"*VagaJuniorFinder | Gerado a {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}.*")

        return "\n".join(md)

    def build_telegram_html(self, scored_jobs: List[ScoredJob]) -> str:
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        
        top_matches = [j for j in scored_jobs if j.score >= 75.0][:8]
        promising_matches = [j for j in scored_jobs if 55.0 <= j.score < 75.0][:8]

        total_recommended = len(top_matches) + len(promising_matches)

        html = []
        html.append(f"<b>Relatório Diário de Vagas — AI &amp; Data Science</b>")
        html.append(f"<b>Candidato:</b> {self.profile.name} | <b>Data:</b> {today_str}\n")
        
        html.append(f"<b>Resumo</b>")
        html.append(f"• Total Recomendadas: <code>{total_recommended}</code> | Destaques (≥75%): <code>{len(top_matches)}</code> | Promissoras (55-74%): <code>{len(promising_matches)}</code>\n")

        # Top Matches Section
        html.append(f"<b>Vagas Destaque (Match ≥ 75%)</b>")
        if not top_matches:
            html.append("<i>Nenhuma vaga atingiu 75% hoje.</i>\n")
        else:
            for sj in top_matches:
                html.append(self._format_job_card_html(sj))

        # Promising Matches Section
        html.append(f"<b>Oportunidades Promissoras (Match 55-74%)</b>")
        if not promising_matches:
            html.append("<i>Nenhuma vaga nesta categoria hoje.</i>\n")
        else:
            for sj in promising_matches:
                html.append(self._format_job_card_html(sj))

        html.append(f"<i>VagaJuniorFinder | {datetime.datetime.now().strftime('%H:%M')}</i>")
        return "\n".join(html)

    def _format_job_card_md(self, sj: ScoredJob) -> str:
        job = sj.job
        lines = []
        lines.append(f"### [{job.title}]({job.link})")
        iefp_tag = " | `Elegível IEFP`" if job.iefp_mentioned else ""
        mode_tag = f"`{job.work_mode}`"
        lines.append(f"**Empresa:** {job.company} &nbsp;|&nbsp; **Localização:** {job.location} &nbsp;|&nbsp; **Fonte:** `{job.source}`")
        lines.append(f"**Match:** `{sj.score}%` &nbsp;|&nbsp; {mode_tag} &nbsp;|&nbsp; **Nível:** `{sj.seniority_status}`{iefp_tag}\n")

        if sj.matched_skills:
            skills_formatted = " ".join([f"`{s}`" for s in sj.matched_skills])
            lines.append(f"**Stack:** {skills_formatted}\n")

        clean_desc = job.description[:260].replace("\n", " ").strip()
        if len(job.description) > 260:
            clean_desc += "..."
        lines.append(f"> {clean_desc}\n")
        lines.append(f"[Candidatar — {job.company}]({job.link})\n")
        lines.append("---\n")
        return "\n".join(lines)

    def _format_job_card_html(self, sj: ScoredJob) -> str:
        job = sj.job
        lines = []
        lines.append(f"📌 <b><a href=\"{job.link}\">{job.title}</a></b>")
        iefp_tag = " | <code>IEFP</code>" if job.iefp_mentioned else ""
        lines.append(f"• <b>Empresa:</b> {job.company} | <b>Local:</b> {job.location}")
        lines.append(f"• <b>Match:</b> <code>{sj.score}%</code> | <code>{job.work_mode}</code>{iefp_tag}")

        if sj.matched_skills:
            skills_formatted = " ".join([f"<code>{s}</code>" for s in sj.matched_skills])
            lines.append(f"• <b>Stack:</b> {skills_formatted}")

        lines.append(f"👉 <a href=\"{job.link}\">Candidatar — {job.company}</a>\n")
        return "\n".join(lines)

    def save_report(self, markdown_content: str, output_dir: str = "reports") -> str:
        os.makedirs(output_dir, exist_ok=True)
        today_filename = f"job_report_{datetime.date.today().isoformat()}.md"
        filepath = os.path.join(output_dir, today_filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return filepath
