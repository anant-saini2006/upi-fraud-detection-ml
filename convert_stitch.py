import re

with open("/Users/anant/.gemini/antigravity-ide/brain/8b4acdc9-c00e-4f69-b420-895aea506d33/.system_generated/steps/283/content.md", "r") as f:
    lines = f.readlines()

html_lines = []
in_html = False
for line in lines:
    if line.startswith("<!DOCTYPE html>"):
        in_html = True
    if in_html:
        html_lines.append(line)

html = "".join(html_lines)

# Convert HTML to JSX
jsx = html.replace('class="', 'className="')
jsx = jsx.replace('<!--', '{/*')
jsx = jsx.replace('-->', '*/}')
jsx = jsx.replace('style="font-variation-settings: \\\'FILL\\\' 1;"', "style={{fontVariationSettings: \"'FILL' 1\"}}")
jsx = jsx.replace('<input class="w-full bg-black/40 border border-white/10 rounded-lg py-2 pl-10 pr-4 text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-colors" placeholder="Search transactions..." type="text">', '<input className="w-full bg-black/40 border border-white/10 rounded-lg py-2 pl-10 pr-4 text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-colors" placeholder="Search transactions..." type="text" />')
jsx = jsx.replace('<img alt="Security Analyst Profile" class="w-10 h-10 rounded-full border border-white/20 object-cover" data-alt="A futuristic, hyper-realistic portrait of a security analyst in a high-tech command center, illuminated by neon green and crimson reflections from monitors. Glassmorphic UI elements float faintly in the background. Cyber-noir aesthetic, high contrast, cinematic lighting." src="https://lh3.googleusercontent.com/aida-public/AB6AXuCVlSt_Ovu4YEqFNZzDzs6BbOVUOqdH3kqNsUpMpKOGUj1NkvTF6QsIcovq7rFxH_dTH7P0AanIb0jJILkE3sBGcFX_A8xsjdjcXQ9TijMOtuIhVeMCkW7hb2iFcjDcy2NXK3ltvRCYXERd345J_BrXZao2b-CV-snj3fT2bptoBFZ_X02zRijgETO9J0DNL-pOXLp8gyHt9zKE8gCb7hfmmGfU7Ig-W7ARGPkPqPM2ojCLsN4Fww8OYso1ZaeIVczPg6SI_PJ1Snll">', '<img alt="Security Analyst Profile" className="w-10 h-10 rounded-full border border-white/20 object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCVlSt_Ovu4YEqFNZzDzs6BbOVUOqdH3kqNsUpMpKOGUj1NkvTF6QsIcovq7rFxH_dTH7P0AanIb0jJILkE3sBGcFX_A8xsjdjcXQ9TijMOtuIhVeMCkW7hb2iFcjDcy2NXK3ltvRCYXERd345J_BrXZao2b-CV-snj3fT2bptoBFZ_X02zRijgETO9J0DNL-pOXLp8gyHt9zKE8gCb7hfmmGfU7Ig-W7ARGPkPqPM2ojCLsN4Fww8OYso1ZaeIVczPg6SI_PJ1Snll" />')
jsx = jsx.replace('<img alt="Sentinel System" class="w-12 h-12 rounded-lg border border-primary-container/30 object-cover" data-alt="A stylized glowing cube representing a sophisticated AI security core, pulsating with neon green energy against a deep obsidian background. Cyber-noir style, hyper-detailed, technical." src="https://lh3.googleusercontent.com/aida-public/AB6AXuBk8e3aj3Jtk7xnuHc_WxR684A44WBXsSx2yf3th76SHLhoAxINnOB3PAbLjPxwT_ZT1tLeZfQ7HIhZDhFNKxvQJoVqauH5jK8R2n-PIDwYALGdQbaM8ZMZUpdzkBXcdMPGTepVC7Q-9DVvd2GMq2dgzPOrkaTKZYSUWdreWQz21jP2bfvxM_gsSoo9Vvsjppbfxc9nlv_9rXhHHe1pMKVCck895rcXB4m3L28tKjEdo1Bp8jLqffjySOQ7A3xRtx2jBypVxIH_jmex">', '<img alt="Sentinel System" className="w-12 h-12 rounded-lg border border-primary-container/30 object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBk8e3aj3Jtk7xnuHc_WxR684A44WBXsSx2yf3th76SHLhoAxINnOB3PAbLjPxwT_ZT1tLeZfQ7HIhZDhFNKxvQJoVqauH5jK8R2n-PIDwYALGdQbaM8ZMZUpdzkBXcdMPGTepVC7Q-9DVvd2GMq2dgzPOrkaTKZYSUWdreWQz21jP2bfvxM_gsSoo9Vvsjppbfxc9nlv_9rXhHHe1pMKVCck895rcXB4m3L28tKjEdo1Bp8jLqffjySOQ7A3xRtx2jBypVxIH_jmex" />')

jsx = jsx.replace('for=', 'htmlFor=')

body_start = jsx.find('<body')
body_end = jsx.find('</body>')
body_content = jsx[body_start:body_end]
# extract classes from body
body_classes = re.search(r'className="([^"]+)"', body_content).group(1)

# get just the children of body
children_start = body_content.find('>') + 1
children = body_content[children_start:]

react_component = f"""
export default function Dashboard() {{
    return (
        <div className="{body_classes}">
            {children}
        </div>
    )
}}
"""

with open("/Users/anant/Documents/UPI Project/frontend/src/app/page.tsx", "w") as f:
    f.write(react_component)
print("Updated page.tsx")
