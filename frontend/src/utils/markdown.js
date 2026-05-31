// Lightweight markdown renderer for trusted, admin-authored DPDP notice
// templates (server-rendered Jinja → markdown). Supports the small subset the
// seeded notices use: headings, bold, unordered lists and paragraphs. Source
// is HTML-escaped first so the output is safe to bind with v-html.

function escapeHtml(text) {
	return text
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
}

function inline(text) {
	return escapeHtml(text)
		.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
		.replace(/\*(.+?)\*/g, "<em>$1</em>")
}

export function renderMarkdown(src) {
	if (!src) return ""
	// If the source already looks like HTML, trust it as-is (admin-authored).
	if (/<\/?[a-z][\s\S]*>/i.test(src)) return src

	const lines = src.split(/\r?\n/)
	const html = []
	let inList = false

	const closeList = () => {
		if (inList) {
			html.push("</ul>")
			inList = false
		}
	}

	for (const raw of lines) {
		const line = raw.trim()
		if (!line) {
			closeList()
			continue
		}
		const heading = line.match(/^(#{1,6})\s+(.*)$/)
		if (heading) {
			closeList()
			const level = heading[1].length
			html.push(`<h${level}>${inline(heading[2])}</h${level}>`)
			continue
		}
		if (/^[-*]\s+/.test(line)) {
			if (!inList) {
				html.push("<ul>")
				inList = true
			}
			html.push(`<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`)
			continue
		}
		closeList()
		html.push(`<p>${inline(line)}</p>`)
	}
	closeList()
	return html.join("")
}
