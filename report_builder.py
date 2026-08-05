import datetime
import html
import os
from typing import List, Optional
from config import CandidateProfile
from matcher import ScoredJob

class ReportBuilder:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def build_markdown(self, scored_jobs: List[ScoredJob], seen_jobs: Optional[List[ScoredJob]] = None) -> str:
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        seen_jobs = seen_jobs or []
        
        top_matches = [j for j in scored_jobs if j.score >= 75.0]
        promising_matches = [j for j in scored_jobs if 55.0 <= j.score < 75.0]
        total_new_recommended = len(top_matches) + len(promising_matches)

        md = []
        md.append(f"# Relatório Diário de Vagas — AI & Data Science (Junior / IEFP)")
        md.append(f"**Candidato:** {self.profile.name} &nbsp;|&nbsp; **Data:** {today_str}\n")

        if total_new_recommended == 0:
            md.append("> ℹ️ **Nota:** Não foram encontradas **vagas novas** qualificadas no scan de hoje.")
            md.append(f"### Resumo")
            md.append(f"- **Vagas Novas:** `0` &nbsp;|&nbsp; **Vagas Ativas Já Vistas Reencontradas:** `{len(seen_jobs)}`\n")
            md.append("---\n")

            md.append(f"## 📋 Vagas Ativas Relevantes (Já Vistas em Execuções Anteriores)\n")
            if not seen_jobs:
                md.append("*Nenhuma vaga ativa qualificada encontrada no histórico recente.*\n")
            else:
                md.append("*As vagas abaixo já foram enviadas em relatórios anteriores, mas continuam ativas nos portais:*\n")
                for sj in seen_jobs[:10]:
                    md.append(self._format_job_card_md(sj, tag="Já Vista"))
        else:
            # Summary Stats
            md.append(f"### Resumo")
            md.append(f"- **Total Novas Recomendadas (≥55%):** `{total_new_recommended}` &nbsp;|&nbsp; **Destaques (≥75%):** `{len(top_matches)}` &nbsp;|&nbsp; **Promissoras (55-74%):** `{len(promising_matches)}`")
            md.append("\n---\n")

            # Top Matches Section
            md.append(f"## Vagas Destaque (Match ≥ 75%)\n")
            if not top_matches:
                md.append("*Nenhuma vaga nova atingiu a pontuação de destaque no dia de hoje (requisitos estritos de 0-1 ano de experiência e âmbito AI/Data).* \n")
            else:
                for sj in top_matches:
                    md.append(self._format_job_card_md(sj))

            md.append("---\n")

            # Promising Matches Section
            md.append(f"## Oportunidades Promissoras (Match 55-74%)\n")
            if not promising_matches:
                md.append("*Nenhuma vaga nova encontrada nesta categoria no dia de hoje.*\n")
            else:
                for sj in promising_matches:
                    md.append(self._format_job_card_md(sj))

            # Include previously seen active jobs if available
            if seen_jobs:
                md.append("---\n")
                md.append(f"## 📋 Vagas Ativas Relevantes (Já Vistas Anteriormente)\n")
                for sj in seen_jobs[:5]:
                    md.append(self._format_job_card_md(sj, tag="Já Vista"))

        md.append("\n---\n")
        md.append(f"*VagaJuniorFinder | Gerado a {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}.*")

        return "\n".join(md)

    def build_telegram_html(self, scored_jobs: List[ScoredJob], seen_jobs: Optional[List[ScoredJob]] = None) -> str:
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        seen_jobs = seen_jobs or []
        
        top_matches = [j for j in scored_jobs if j.score >= 75.0][:8]
        promising_matches = [j for j in scored_jobs if 55.0 <= j.score < 75.0][:8]
        total_new_recommended = len(top_matches) + len(promising_matches)

        html = []
        html.append(f"<b>Relatório Diário de Vagas — AI &amp; Data Science</b>")
        html.append(f"<b>Candidato:</b> {self.profile.name} | <b>Data:</b> {today_str}\n")

        if total_new_recommended == 0:
            html.append("ℹ️ <b>Não foram encontradas vagas novas no scan de hoje.</b>")
            html.append("<i>Todas as vagas detetadas hoje já foram enviadas em relatórios anteriores.</i>\n")

            html.append("<b>📋 Vagas Ativas Relevantes (Já Vistas):</b>")
            if not seen_jobs:
                html.append("<i>Nenhuma vaga qualificada encontrada no histórico recente.</i>\n")
            else:
                for sj in seen_jobs[:5]:
                    html.append(self._format_job_card_html(sj, tag="Já Vista"))
        else:
            html.append(f"<b>Resumo</b>")
            html.append(f"• Novas Recomendadas: <code>{total_new_recommended}</code> | Destaques: <code>{len(top_matches)}</code> | Promissoras: <code>{len(promising_matches)}</code>\n")

            # Top Matches Section
            html.append(f"<b>Vagas Destaque (Match ≥ 75%)</b>")
            if not top_matches:
                html.append("<i>Nenhuma vaga nova atingiu 75% hoje.</i>\n")
            else:
                for sj in top_matches:
                    html.append(self._format_job_card_html(sj))

            # Promising Matches Section
            html.append(f"<b>Oportunidades Promissoras (Match 55-74%)</b>")
            if not promising_matches:
                html.append("<i>Nenhuma vaga nova nesta categoria hoje.</i>\n")
            else:
                for sj in promising_matches:
                    html.append(self._format_job_card_html(sj))

        html.append(f"<i>VagaJuniorFinder | {datetime.datetime.now().strftime('%H:%M')}</i>")
        return "\n".join(html)

    def _format_job_card_md(self, sj: ScoredJob, tag: str = "") -> str:
        job = sj.job
        lines = []
        title_suffix = f" `{tag}`" if tag else ""
        lines.append(f"### [{job.title}]({job.link}){title_suffix}")
        iefp_tag = " | `Elegível IEFP`" if job.iefp_mentioned else ""
        mode_tag = f"`{job.work_mode}`"
        lines.append(f"**Empresa:** {job.company} &nbsp;|&nbsp; **Localização:** {job.location} &nbsp;|&nbsp; **Fonte:** `{job.source}`")
        lines.append(f"**Match:** `{sj.score}%` &nbsp;|&nbsp; {mode_tag} &nbsp;|&nbsp; **Nível:** `{sj.seniority_status}`{iefp_tag}\n")

        if sj.matched_skills:
            skills_formatted = " ".join([f"`{s}`" for s in sj.matched_skills])
            lines.append(f"**Stack:** {skills_formatted}\n")

        if sj.ai_evaluated and sj.ai_reasoning:
            lines.append(f"🤖 **Análise IA:** *{sj.ai_reasoning}*\n")

        clean_desc = job.description[:260].replace("\n", " ").strip()
        if len(job.description) > 260:
            clean_desc += "..."
        lines.append(f"> {clean_desc}\n")
        lines.append(f"[Candidatar — {job.company}]({job.link})\n")
        lines.append("---\n")
        return "\n".join(lines)

    def _format_job_card_html(self, sj: ScoredJob, tag: str = "") -> str:
        job = sj.job
        lines = []
        safe_title = html.escape(job.title)
        safe_company = html.escape(job.company)
        safe_location = html.escape(job.location)
        tag_badge = f" [<i>{html.escape(tag)}</i>]" if tag else ""
        
        lines.append(f"📌 <b><a href=\"{job.link}\">{safe_title}</a></b>{tag_badge}")
        iefp_tag = " | <code>IEFP</code>" if job.iefp_mentioned else ""
        lines.append(f"• <b>Empresa:</b> {safe_company} | <b>Local:</b> {safe_location}")
        lines.append(f"• <b>Match:</b> <code>{sj.score}%</code> | <code>{html.escape(job.work_mode)}</code>{iefp_tag}")

        if sj.matched_skills:
            skills_formatted = " ".join([f"<code>{html.escape(s)}</code>" for s in sj.matched_skills])
            lines.append(f"• <b>Stack:</b> {skills_formatted}")

        if sj.ai_evaluated and sj.ai_reasoning:
            safe_ai = html.escape(sj.ai_reasoning)
            lines.append(f"🤖 <b>Análise IA:</b> <i>{safe_ai}</i>")

        lines.append(f"👉 <a href=\"{job.link}\">Candidatar — {safe_company}</a>\n")
        return "\n".join(lines)

    def save_report(self, markdown_content: str, output_dir: str = "reports") -> str:
        os.makedirs(output_dir, exist_ok=True)
        today_filename = f"job_report_{datetime.date.today().isoformat()}.md"
        filepath = os.path.join(output_dir, today_filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return filepath
