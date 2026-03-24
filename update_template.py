import re

# Read template
with open('Template4.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update MATCHES
matches_html = """
{% for match in MATCHES %}
<div class="glass-card p-6 rounded-2xl hover:translate-y-[-4px] transition-transform duration-300">
<div class="flex justify-between items-start mb-4">
<div class="w-12 h-12 rounded-xl bg-blue-100 text-primary flex items-center justify-center text-xl">
<i class="fas {{match.ICON}}">
</i>
</div>
<span class="bg-blue-50 text-blue-600 tag-pill">{{match.BADGE}}</span>
</div>
<h4 class="font-display font-bold text-slate-900 mb-2">{{match.TITLE}}</h4>
<p class="text-sm text-slate-600 leading-relaxed mb-4">{{match.DESC}}</p>
<div class="flex gap-2">
{% if match.TAG_1 %}<span class="bg-slate-100 text-slate-600 px-2 py-1 rounded text-[10px] font-bold">{{match.TAG_1}}</span>{% endif %}
{% if match.TAG_2 %}<span class="bg-slate-100 text-slate-600 px-2 py-1 rounded text-[10px] font-bold">{{match.TAG_2}}</span>{% endif %}
</div>
</div>
{% endfor %}
"""

# Replace the 3 hardcoded match cards
# Using regex to find the grid container and replace its contents
html = re.sub(
    r'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">.*?<div class="md:col-span-2 lg:col-span-3 bg-slate-900',
    r'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">\n' + matches_html.replace('\\', '\\\\') + r'\n<div class="md:col-span-2 lg:col-span-3 bg-slate-900',
    html,
    flags=re.DOTALL
)

# 2. Update GAP
gap_html = """
{% if GAP_TITLE %}
<div class="md:col-span-2 lg:col-span-3 bg-slate-900 p-8 rounded-3xl text-white relative overflow-hidden">
<div class="absolute right-0 bottom-0 opacity-10">
<i class="fas {{GAP_ICON}} text-[120px]">
</i>
</div>
<div class="flex flex-col md:flex-row gap-8 items-center relative z-10">
<div class="md:w-2/3">
<div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-blue-300 text-[10px] font-bold mb-4 uppercase tracking-[0.2em]">
<i class="fa-solid fa-puzzle-piece">
</i> Transferable Edge</div>
<h3 class="text-2xl font-display font-bold mb-3">{{GAP_TITLE}}</h3>
<p class="text-slate-300 text-sm leading-relaxed">{{GAP_DESC}}</p>
</div>
<div class="md:w-1/3 w-full bg-white/5 p-6 rounded-2xl border border-white/10">
<div class="flex justify-between items-center mb-2">
<span class="text-xs font-bold text-slate-400">System Adaptability</span>
<span class="text-xs font-black text-blue-400">High</span>
</div>
<div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
<div class="bg-primary h-full rounded-full w-[92%]">
</div>
</div>
</div>
</div>
</div>
{% endif %}
"""

html = re.sub(
    r'<div class="md:col-span-2 lg:col-span-3 bg-slate-900.*?</div>\n</div>\n</div>\n</div>',
    gap_html.replace('\\', '\\\\') + '\n</div>',
    html,
    flags=re.DOTALL
)

# 3. Update EXPERIENCE
experience_html = """
{% if EXPERIENCES %}
{% for exp in EXPERIENCES %}
<div class="relative pl-8 before:content-[''] before:absolute before:left-0 before:top-2 before:bottom-0 before:w-0.5 before:bg-blue-100">
<div class="absolute left-[-4px] top-2 w-2.5 h-2.5 rounded-full {% if loop.first %}bg-primary ring-4 ring-blue-50{% else %}bg-slate-300{% endif %}">
</div>
<div class="flex flex-wrap justify-between items-baseline gap-2 mb-2">
<h4 class="text-xl font-bold text-slate-900">{{exp.TITLE}}</h4>
<span class="text-sm font-bold text-slate-400">{{exp.DATES}}</span>
</div>
<p class="text-secondary font-bold text-sm mb-4">{{exp.COMPANY}}</p>
<ul class="space-y-3">
{% for bullet in exp.BULLETS %}
<li class="text-slate-600 text-sm leading-relaxed flex gap-3">
<span class="text-blue-400 mt-1.5">•</span>
 <span>{{bullet}}</span>
</li>
{% endfor %}
</ul>
</div>
{% endfor %}
{% endif %}
"""

html = re.sub(
    r'<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-\[0.2em\] mb-6">Professional Experience</h3>\n<div class="space-y-12">.*?</ul>\n</div>\n</div>',
    '<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-[0.2em] mb-6">Professional Experience</h3>\n<div class="space-y-12">\n' + experience_html.replace('\\', '\\\\') + '\n</div>',
    html,
    flags=re.DOTALL
)


# 4. Update TECHNICAL ECOSYSTEM
eco_html = """
{% if TECHNOLOGIES %}
<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-[0.2em] mb-6">Technical Ecosystem</h3>
<div class="space-y-6">
{% for tech in TECHNOLOGIES %}
<div>
<h5 class="text-[10px] font-black text-slate-400 uppercase mb-2 tracking-tighter">{{tech.LABEL}}</h5>
<p class="text-xs font-bold text-slate-700 leading-relaxed">{{tech.VALUE}}</p>
</div>
{% endfor %}
</div>
{% endif %}
"""
html = re.sub(
    r'<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-\[0.2em\] mb-6">Technical Ecosystem</h3>\n<div class="space-y-6">.*?</div>\n</div>\n</div>',
    eco_html.replace('\\', '\\\\') + '\n</div>',
    html,
    flags=re.DOTALL
)

# 5. Update EXPERTISE
expertise_html = """
{% if EXPERTISE %}
<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-[0.2em] mb-6">Expertise</h3>
<div class="space-y-4">
{% for comp in EXPERTISE %}
<div>
<p class="text-xs font-bold text-slate-900 mb-1">{{comp.LABEL}}</p>
<p class="text-[11px] text-slate-500 leading-tight">{{comp.SKILLS}}</p>
</div>
{% endfor %}
</div>
{% endif %}
"""
html = re.sub(
    r'<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-\[0.2em\] mb-6">Expertise</h3>\n<div class="space-y-4">.*?</div>\n</div>\n</div>',
    expertise_html.replace('\\', '\\\\') + '\n</div>',
    html,
    flags=re.DOTALL
)


# 6. Update EDUCATION
edu_html = """
{% if EDUCATIONS %}
<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-[0.2em] mb-6">Education & Certs</h3>
<div class="space-y-4">
{% for edu in EDUCATIONS %}
<div class="border-l-2 border-slate-100 pl-4">
<p class="text-[11px] font-bold text-slate-700">{{edu}}</p>
</div>
{% endfor %}
</div>
{% endif %}
"""
html = re.sub(
    r'<h3 class="font-display text-xs font-black text-slate-400 uppercase tracking-\[0.2em\] mb-6">Education & Certs</h3>\n<div class="space-y-4">.*?</div>\n</div>\n</div>\n</div>\n</div>',
    edu_html.replace('\\', '\\\\') + '\n</div>\n</div>\n</div>',
    html,
    flags=re.DOTALL
)


with open('Template4.html', 'w', encoding='utf-8') as f:
    f.write(html)
