let model
let drafts = {}
let feedback = []
let reviews = []
const filters = { priority: '', state: '', person: '' }
const attentionLabels = { waiting: 'Waiting for response', clarification: 'Clarification needed', conflict: 'Decision needed' }
const $ = selector => document.querySelector(selector)
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;')
const allQuestions = () => model.requirements.flatMap(r => r.questions.map(q => ({ ...q, requirement: r.id, priority: r.priority })))
const draftKey = () => `questionnaire:${model.id}:drafts`

function saveDrafts() {
  try { sessionStorage.setItem(draftKey(), JSON.stringify(drafts)); return true }
  catch { $('#load-status').textContent = 'Draft storage is unavailable. Keep this tab open; copy unsent text before reloading.'; return false }
}

function render() {
  document.title = model.title
  for (const key of ['title', 'intro', 'notice']) $(`#${key}`).textContent = model[key]
  $('#setup').hidden = !model.setup
  if (model.setup) $('#setup-content').innerHTML = Object.entries({ outcome: 'Outcome', out_of_scope: 'Outside this review', readers: 'Readers', response_budget: 'Response budget', reviewer: 'Review and fallback', decision_maker: 'Decision authority', escalation: 'Escalation' }).map(([key, label]) => `<p><strong>${label}</strong><br>${esc(model.setup[key])}</p>`).join('')
  $('#priorities').innerHTML = ['', ...new Set(model.requirements.map(r => r.priority))].map(p => `<button data-priority="${esc(p)}" aria-pressed="false">${esc(p || 'All priorities')}</button>`).join('')
  $('#person').innerHTML = '<option value="">Everyone</option><option value="__anyone">Anyone</option>' + [...new Set(allQuestions().flatMap(q => q.people))].sort().map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join('')
  $('#requirements').innerHTML = model.requirements.map(r => `<article class="card" id="requirement-${r.id}">
    <p class="eyebrow">${esc(r.priority)} priority</p><h2>${esc(r.title)}</h2><p>${esc(r.text)}</p>
    ${r.details ? `<details class="scope"><summary>Requirement details</summary><p>${esc(r.details)}</p></details>` : ''}
    <div class="questions">${r.questions.map(q => `<details class="question" id="question-${q.id}">
      <summary><span>${esc(q.title)}</span><small>${q.status === 'answered' ? '✓ Answered' : 'Open'} · For ${esc(q.people.join(', ') || 'Anyone')}</small></summary>
      <p>${esc(q.prompt)}</p>${q.follow_up_to ? `<p class="muted">Follow-up to <a href="#question-${q.follow_up_to}">${esc(allQuestions().find(p => p.id === q.follow_up_to).title)}</a></p>` : ''}
      ${q.request && q.status === 'open' ? `<p><strong>Recommendation</strong> ${esc(q.request.recommendation)}</p><p><strong>Why it matters</strong> ${esc(q.request.why)}</p><p><strong>How to answer</strong> ${esc(q.request.response)}</p>` : ''}
      <p class="review-note" data-attention="${q.id}" hidden></p>
      ${q.attention?.evidence ? `<p>${q.attention.evidence.map(e => `<a href="${esc(e.href)}" rel="noreferrer">${esc(e.label)}</a>`).join(' · ')}</p>` : ''}
      ${q.answer ? `<div class="answer"><strong>Answer</strong><p>${esc(q.answer.text)}</p>${q.answer.evidence.map(e => `<a href="${esc(e.href)}" rel="noreferrer">${esc(e.label)}</a>`).join(' · ')}</div>` : ''}
      <details class="feedback"><summary>${q.status === 'answered' ? 'Add clarification' : 'Answer or give feedback'}</summary>
        <form data-question="${q.id}"><div class="form-row">
          <label>Your name<input name="name" required maxlength="80" autocomplete="name"></label>
          <label>Your response<select name="kind"><option value="answer">Answer</option><option value="change">Suggest a change</option><option value="question">Ask a question</option><option value="agree">Agree</option></select></label>
        </div><label>Feedback on “${esc(q.title)}”<textarea name="message" rows="3" maxlength="3000"></textarea></label>
        <button type="submit">Send feedback</button><p class="status" role="status"></p></form>
      </details><div data-responses="${q.id}"></div>
    </details>`).join('')}</div></article>`).join('')
  for (const form of document.querySelectorAll('form')) {
    const id = form.dataset.question
    const draft = drafts[id]
    if (draft) {
      for (const field of ['name', 'kind', 'message']) form.elements[field].value = draft[field] ?? ''
      if (draft.message || draft.pending) { form.closest('.feedback').open = true; form.closest('.question').open = true }
    }
    const capture = () => {
      drafts[id] = { ...drafts[id], ...Object.fromEntries(new FormData(form)) }
      form.elements.message.required = form.elements.kind.value !== 'agree'
      saveDrafts()
    }
    form.elements.message.required = form.elements.kind.value !== 'agree'
    form.addEventListener('input', capture)
    form.addEventListener('change', capture)
    form.addEventListener('submit', async event => {
      event.preventDefault()
      capture()
      const status = form.querySelector('.status')
      const button = form.querySelector('button')
      const payload = { question: id, name: form.elements.name.value, kind: form.elements.kind.value, message: form.elements.message.value }
      const fingerprint = JSON.stringify(payload)
      if (drafts[id].pending?.fingerprint !== fingerprint) drafts[id].pending = { fingerprint, id: crypto.randomUUID() }
      const submissionId = drafts[id].pending.id
      saveDrafts()
      button.disabled = true
      status.textContent = 'Saving…'
      try {
        const response = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, id: submissionId }) })
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || 'Save failed')
        delete drafts[id].pending
        if (form.elements.message.value === payload.message) form.elements.message.value = ''
        capture()
        status.textContent = 'Saved. Pending review; saving does not mark the question answered.'
        await refresh().catch(() => { status.textContent = 'Saved. Review updates are unavailable; reload later to see the receipt.' })
      } catch (error) { status.textContent = `${error.message}. Your text and retry ID are kept.` }
      finally { button.disabled = false }
    })
  }
}

function applyFilters() {
  const scoped = allQuestions().filter(q => (!filters.priority || q.priority === filters.priority) && (!filters.person || (filters.person === '__anyone' ? !q.people.length : q.people.includes(filters.person))))
  const visible = scoped.filter(q => !filters.state || q.status === filters.state)
  for (const state of ['open', 'answered']) $(`#${state}-count`).textContent = scoped.filter(q => q.status === state).length
  for (const button of document.querySelectorAll('[data-priority]')) button.setAttribute('aria-pressed', String(button.dataset.priority === filters.priority))
  for (const button of document.querySelectorAll('[data-state]')) button.setAttribute('aria-pressed', String(button.dataset.state === filters.state))
  $('#person').value = filters.person
  for (const q of allQuestions()) document.getElementById(`question-${q.id}`).hidden = !visible.some(v => v.id === q.id)
  for (const r of model.requirements) document.getElementById(`requirement-${r.id}`).hidden = !visible.some(q => q.requirement === r.id)
  $('#empty').hidden = visible.length > 0
  $('#filter-status').textContent = `${visible.length} ${visible.length === 1 ? 'question' : 'questions'} · ${filters.priority || 'All priorities'} · ${filters.person === '__anyone' ? 'Anyone' : filters.person || 'Everyone'}`
  const navigation = ['open', 'answered'].map(state => {
    const entries = visible.filter(q => q.status === state)
    return entries.length ? `<h3>${state === 'open' ? 'Open' : 'Completed'} (${entries.length})</h3><ul>${entries.map(q => `<li><a href="#question-${q.id}">${esc(q.title)}<small>${esc(q.people.join(', ') || 'Anyone')}</small></a></li>`).join('')}</ul>` : ''
  }).join('')
  if ($('#question-nav').innerHTML !== navigation) $('#question-nav').innerHTML = navigation
  showAttention(visible)
}

function showAttention(visible) {
  const pending = feedback.filter(row => !reviews.some(r => r.feedback_id === row.id))
  const counts = { waiting: 0, clarification: 0, conflict: 0 }
  const items = []
  for (const q of allQuestions()) {
    const unreviewed = pending.filter(row => row.question === q.id).length
    const attention = q.status === 'open' ? q.attention || { state: q.follow_up_to ? 'clarification' : 'waiting', next_action: `${q.people.join(', ') || 'A respondent still to be identified'} can answer this question.` } : null
    const label = attention ? `${attentionLabels[attention.state]}. ${attention.next_action}` : ''
    const note = [unreviewed ? `${unreviewed} ${unreviewed === 1 ? 'response' : 'responses'} received, awaiting review. Review contact: ${model.setup?.reviewer || 'the reviewer'}` : '', label].filter(Boolean).join(' ')
    const box = document.querySelector(`[data-attention="${q.id}"]`)
    box.textContent = note
    box.hidden = !note
    if (visible.some(v => v.id === q.id)) {
      if (attention) counts[attention.state]++
      if (note) items.push(`<p><a href="#question-${q.id}">${esc(q.title)}</a><br>${esc(note)}</p>`)
    }
  }
  const pendingCount = pending.filter(row => visible.some(q => q.id === row.question)).length
  $('#attention-counts').textContent = `${pendingCount} ${pendingCount === 1 ? 'response' : 'responses'} awaiting review · ${counts.waiting} waiting for response · ${counts.clarification} need clarification · ${counts.conflict} need a decision. Current filters; categories can overlap.`
  const actions = items.join('') || '<p>No next actions in these filters.</p>'
  if ($('#attention-items').innerHTML !== actions) $('#attention-items').innerHTML = actions
  const latest = reviews.reduce((a, b) => !a || Date.parse(b.reviewed_at) > Date.parse(a.reviewed_at) ? b : a, null)
  $('#last-review').textContent = latest ? `Last review across this page: ${latest.reviewed_at}. Question states shown from revision ${model.revision}.` : 'No responses reviewed yet.'
  const interpretation = latest ? `Latest interpretation across this page: <a href="#feedback-${latest.feedback_id}">${esc(latest.summary)}</a>` : ''
  if ($('#latest-review').innerHTML !== interpretation) $('#latest-review').innerHTML = interpretation
}

function reveal() {
  let id
  try { id = decodeURIComponent(location.hash.slice(1)) } catch { return }
  const target = document.getElementById(id)
  if (!target) return
  if (target.closest('[hidden]')) { Object.assign(filters, { priority: '', state: '', person: '' }); applyFilters() }
  for (let node = target; node; node = node.parentElement) if (node.tagName === 'DETAILS') node.open = true
  target.scrollIntoView({ block: 'start' })
}

function showFeedback(rows) {
  for (const box of document.querySelectorAll('[data-responses]')) {
    box.innerHTML = rows.filter(row => row.question === box.dataset.responses).map(row => {
      const review = reviews.find(r => r.feedback_id === row.id)
      const state = review ? `Reviewed: ${review.summary}` : row.receipt ? 'Reviewer notified. Pending review.' : `Saved. Pending delivery to reviewer${row.attempts ? ` (${row.attempts} attempts)` : ''}.`
      return `<div class="response" id="feedback-${row.id}"><strong>${esc(row.name)} · ${esc(row.kind)}</strong><p>${esc(row.message)}</p><small>${esc(row.created_at)} · self-entered name</small><p class="review-note">${esc(state)}</p></div>`
    }).join('')
  }
}

async function refresh() {
  const response = await fetch('/api/state', { cache: 'no-store' })
  if (!response.ok) throw new Error('Could not load review updates')
  const state = await response.json()
  feedback = state.feedback
  reviews = state.model.reviews
  if (!model) {
    model = state.model
    try { drafts = JSON.parse(sessionStorage.getItem(draftKey()) || '{}') } catch { drafts = {} }
    render()
    $('.question-index').open = matchMedia('(min-width: 56rem)').matches
  }
  $('#delivery-mode').textContent = state.mode === 'automatic' ? 'Feedback is saved before notification. Delivery and review receipts appear below each response.' : 'Manual review only: feedback is saved here, but no automatic wake-up is configured. Send the reviewer this page link and ask them to review pending responses.'
  $('#update').hidden = state.model.revision === model.revision
  showFeedback(state.feedback)
  applyFilters()
}

document.addEventListener('click', event => {
  const button = event.target.closest('button')
  if (button?.dataset.priority !== undefined) { filters.priority = button.dataset.priority; applyFilters() }
  if (button?.dataset.state) { filters.state = filters.state === button.dataset.state ? '' : button.dataset.state; applyFilters() }
  const link = event.target.closest('a[href^="#"]')
  if (link) { event.preventDefault(); history.replaceState(null, '', link.getAttribute('href')); reveal() }
})
$('#person').addEventListener('change', event => { filters.person = event.target.value; applyFilters() })
$('#reset').addEventListener('click', () => { Object.assign(filters, { priority: '', state: '', person: '' }); applyFilters() })
$('#reload').addEventListener('click', () => { if (saveDrafts()) location.reload() })
window.addEventListener('hashchange', reveal)
refresh().then(reveal).catch(() => { $('#load-status').textContent = 'Could not load this questionnaire. Reload to retry.' })
setInterval(() => { if (model && document.visibilityState === 'visible') refresh().catch(() => { $('#load-status').textContent = 'Updates unavailable. Saved feedback is unaffected; drafts remain in this tab.' }) }, 5000)
