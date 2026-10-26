let model
let drafts = {}
let feedback = []
let reviews = []
let selectedId
let acceptingFeedback = true
const filters = { priority: new Set(), person: new Set(), state: new Set() }
const attentionLabels = { waiting: 'Waiting for an answer', clarification: 'Needs more detail', conflict: 'Needs a decision' }
const statusLabels = { open: 'Open', answered: 'Answered', deferred: 'Deferred', proposed: 'Proposed answer', pending: 'Needs review', ...attentionLabels }
const symbols = { waiting: '…', clarification: '?', conflict: '!', answered: '✓', deferred: '–', pending: '↻' }
const desktop = matchMedia('(min-width: 64rem)')
const $ = selector => document.querySelector(selector)
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;')
const allQuestions = () => model.requirements.flatMap(r => r.questions.map(q => ({ ...q, requirement: r.id, priority: r.priority, context: `${r.title} ${r.text} ${r.details || ''}` })))
const draftKey = () => `questionnaire:${model.id}:drafts`
const attentionFor = q => q.status !== 'open' ? null : q.attention || { state: q.follow_up_to ? 'clarification' : 'waiting', next_action: `${q.people.join(', ') || 'A respondent still to be identified'} can answer this question.` }
const pendingFor = id => feedback.filter(row => row.question === id && !reviews.some(r => r.feedback_id === row.id)).length
const proposalsFor = q => {
  const acceptance = feedback.find(f => f.id === q.answer?.acceptance_id)
  return feedback.filter(f => f.question === q.id && ['propose', 'adopt'].includes(f.kind) && (!acceptance || f.created_at > acceptance.created_at))
}
const decisionsFor = proposal => feedback.filter(f => f.context?.proposal_id === proposal.id && ['accept', 'correct'].includes(f.kind))
const queuedFor = q => proposalsFor(q).filter(p => !decisionsFor(p).some(d => !reviews.some(r => r.feedback_id === d.id)))
const filterLabel = (group, value) => group === 'state' ? statusLabels[value] : group === 'person' && value === '__anyone' ? 'Anyone' : value
const responseKinds = {
  answer: { choice: 'Answer the question', label: 'Your answer', hint: 'Give the information requested above. You can also say you are not sure.', button: 'Save answer' },
  propose: { choice: 'Propose an answer for SME review', label: 'Your proposed answer', hint: 'A candidate for an SME to accept or correct. Saving a proposal does not settle the question.', button: 'Save proposal' },
  adopt: { choice: 'Use recommendation as proposal', label: 'Recommendation to propose', hint: 'The exact recommendation and its revision will be saved as your proposal. Choose Propose an answer to edit it first.', button: 'Save proposal' },
  change: { choice: 'Suggest a change', label: 'What should change, and why?', hint: 'Describe the change and give an example or evidence.', button: 'Save suggestion' },
  question: { choice: 'Ask a question', label: 'What needs clarification?', hint: 'Ask what you need to know before you can answer.', button: 'Save question' },
  agree: { choice: 'Agree with the recommendation', label: 'Anything to add? (optional)', hint: 'You can save your agreement without a note.', button: 'Save agreement' },
}

function matchesGroup(q, group, value) {
  if (group === 'priority') return q.priority === value
  if (group === 'person') return value === '__anyone' ? !q.people.length : q.people.includes(value)
  if (value === 'pending') return pendingFor(q.id) > 0
  if (value === 'proposed') return queuedFor(q).length > 0
  return q.status === value || attentionFor(q)?.state === value
}

function matchesFilters(q) {
  const words = $('#search').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  const text = `${q.title} ${q.prompt} ${q.people.join(' ')} ${q.context}`.toLocaleLowerCase()
  return words.every(word => text.includes(word)) && Object.entries(filters).every(([group, values]) => !values.size || [...values].some(value => matchesGroup(q, group, value)))
}

function clearFilters() {
  for (const values of Object.values(filters)) values.clear()
  $('#search').value = ''
  applyFilters()
}

function saveDrafts() {
  try { sessionStorage.setItem(draftKey(), JSON.stringify(drafts)); return true }
  catch { $('#load-status').textContent = 'Draft storage is unavailable. Keep this tab open; copy unsent text before reloading.'; return false }
}

function render() {
  document.title = model.title
  for (const key of ['title', 'intro', 'notice']) $(`#${key}`).textContent = model[key]
  $('#setup').hidden = !model.setup
  if (model.setup) $('#setup-content').innerHTML = Object.entries({ outcome: 'Outcome', out_of_scope: 'Outside this review', readers: 'Readers', response_budget: 'Response budget', reviewer: 'Review and fallback', decision_maker: 'Decision authority', escalation: 'Escalation' }).map(([key, label]) => `<p><strong>${label}</strong><br>${esc(model.setup[key])}</p>`).join('')
  const options = (group, values) => values.map(value => `<label class="filter-option"><input type="checkbox" data-filter="${group}" value="${esc(value)}"><span>${esc(filterLabel(group, value))}</span><span class="count"></span></label>`).join('')
  const people = [...new Set(allQuestions().flatMap(q => q.people))].sort()
  $('#priorities').innerHTML = options('priority', [...new Set(model.requirements.map(r => r.priority))])
  $('#people').innerHTML = options('person', people.concat('__anyone'))
  $('#statuses').innerHTML = options('state', Object.keys(statusLabels))
  $('#question-nav').innerHTML = allQuestions().map(q => {
    const state = attentionFor(q)?.state || q.status
    return `<li data-entry="${q.id}"><a href="#question-${q.id}" aria-current="false"><span class="symbol" data-tone="${state}" aria-hidden="true">${symbols[state]}</span><span class="question-preview"><strong>${esc(q.title)}</strong><small>Who can answer: ${esc(q.people.join(', ') || 'Anyone')}</small><span class="badge" data-tone="${state}">${statusLabels[state]}</span><small class="pending" hidden></small></span></a></li>`
  }).join('')
  $('#requirements').innerHTML = model.requirements.map(r => `<article class="card" id="requirement-${r.id}">
    ${r.questions.map(q => `<section class="question" id="question-${q.id}">
      <div class="question-header"><span class="badge" data-tone="${attentionFor(q)?.state || q.status}">${statusLabels[attentionFor(q)?.state || q.status]}</span><span class="badge">${esc(r.priority)} priority</span></div>
      <h2 tabindex="-1">${esc(q.title)}</h2>
      <p>${esc(q.prompt)}</p>${q.follow_up_to ? `<p class="muted">Follow-up to <a href="#question-${q.follow_up_to}">${esc(allQuestions().find(p => p.id === q.follow_up_to).title)}</a></p>` : ''}
      ${q.request && q.status === 'open' ? `<div class="recommendation"><strong>Recommendation · not an answer</strong><p>${esc(q.request.recommendation)}</p>${model.state !== 'closed' ? `<button type="button" class="secondary" data-adopt="${q.id}">Use as proposal</button>` : ''}</div>` : ''}
      <dl class="roles"><div><dt>Who can answer</dt><dd>${esc(q.people.join(', ') || 'Anyone')}</dd></div><div><dt>Who decides</dt><dd>${esc(model.setup?.decision_maker || 'Ask the questionnaire owner.')}</dd></div></dl>
      ${q.answer ? `<div class="answer" data-tone="${q.answer.acceptance_id ? 'answered' : 'recorded'}"><strong>${q.answer.acceptance_id ? 'Accepted answer' : 'Answer'}</strong><p>${esc(q.answer.text)}</p>${q.answer.evidence.map(e => `<a href="${esc(e.href)}" rel="noreferrer">${esc(e.label)}</a>`).join(' · ')}</div>` : ''}
      <div data-proposals="${q.id}"></div>
      ${q.status === 'deferred' ? `<p class="review-note"><strong>Deferred — not answered.</strong> ${esc(q.deferral)}</p>` : ''}
      ${model.state === 'closed' && drafts[q.id]?.message ? `<label>Unsent draft (not submitted)<textarea readonly>${esc(drafts[q.id].message)}</textarea></label>` : ''}
      ${model.state === 'closed' ? '' : `<form class="feedback" data-question="${q.id}" aria-label="Feedback on ${esc(q.title)}">
        <fieldset><legend>What would you like to do?</legend>${Object.entries(responseKinds).map(([kind, copy]) => `<label class="response-option" ${kind === 'adopt' ? 'hidden' : ''}><input type="radio" name="kind" value="${kind}" ${kind === 'answer' ? 'checked' : ''}><span>${esc(kind === 'agree' ? q.answer ? 'Agree with the answer' : q.request ? copy.choice : 'Express agreement' : copy.choice)}</span></label>`).join('')}</fieldset>
        <label><span data-message-label>Your answer</span><textarea name="message" rows="3" maxlength="3000" aria-describedby="message-hint-${q.id}"></textarea></label>
        <p class="muted message-hint" id="message-hint-${q.id}"></p>
        <label>Your name<select name="person" required><option value="">Choose your name</option>${people.map(name => `<option value="person:${esc(name)}">${esc(name)}</option>`).join('')}<option value="other">Other</option></select></label>
        <label data-other-name hidden>Enter your name<input name="name" maxlength="80" autocomplete="name" disabled></label>
        <p class="muted">Names are self-reported. You can contribute even if you are not the named respondent.</p>
        <button type="submit">Save answer</button><p class="status" role="status"></p>
      </form>`}
      <div class="previous-feedback" data-responses="${q.id}"></div>
      <details class="context"><summary>Requirement details</summary><h3>${esc(r.title)}</h3><p>${esc(r.text)}</p>${r.details ? `<p>${esc(r.details)}</p>` : ''}${q.request ? `<p><strong>Why it matters</strong> ${esc(q.request.why)}</p>` : ''}</details>
      <p class="review-note" data-attention="${q.id}" hidden></p>
      ${q.attention?.evidence ? `<p>${q.attention.evidence.map(e => `<a href="${esc(e.href)}" rel="noreferrer">${esc(e.label)}</a>`).join(' · ')}</p>` : ''}
      <p class="muted" data-save-notice></p>
    </section>`).join('')}</article>`).join('')
  $('#reviewer-name').value = drafts.reviewerName || ''
  for (const form of document.querySelectorAll('form.feedback')) {
    const id = form.dataset.question
    const question = allQuestions().find(q => q.id === id)
    const draft = drafts[id]
    if (draft) {
      for (const field of ['kind', 'message']) form.elements[field].value = draft[field] ?? (field === 'kind' ? 'answer' : '')
      form.elements.person.value = draft.person === 'other' ? 'other' : people.includes(draft.name) ? `person:${draft.name}` : draft.name ? 'other' : ''
      form.elements.name.value = form.elements.person.value === 'other' ? draft.name ?? '' : draft.otherName ?? ''
    }
    const updateFields = () => {
      const kind = form.elements.kind.value
      const copy = responseKinds[kind]
      form.querySelector('[data-message-label]').textContent = copy.label
      form.querySelector('.message-hint').textContent = kind === 'answer' && question.request ? question.request.response : copy.hint
      form.querySelector('button').textContent = copy.button
      form.elements.message.required = kind !== 'agree'
      form.elements.message.readOnly = kind === 'adopt'
      const other = form.elements.person.value === 'other'
      form.querySelector('[data-other-name]').hidden = !other
      form.elements.name.disabled = !other
      form.elements.name.required = other
    }
    const respondent = () => form.elements.person.value === 'other' ? form.elements.name.value : form.elements.person.value.slice('person:'.length)
    const capture = () => {
      updateFields()
      drafts[id] = { ...drafts[id], name: respondent(), person: form.elements.person.value, otherName: form.elements.name.value, kind: form.elements.kind.value, message: form.elements.message.value }
      saveDrafts()
    }
    updateFields()
    form.addEventListener('input', capture)
    form.addEventListener('change', capture)
    form.addEventListener('submit', async event => {
      event.preventDefault()
      capture()
      const status = form.querySelector('.status')
      const button = form.querySelector('button')
      const payload = { question: id, name: respondent(), kind: form.elements.kind.value, message: form.elements.message.value }
      if (['propose', 'adopt'].includes(payload.kind)) payload.context = { revision: model.revision }
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
        if (payload.kind === 'adopt') form.elements.kind.value = 'answer'
        capture()
        status.textContent = ['propose', 'adopt'].includes(payload.kind) ? 'Proposal saved. Awaiting SME acceptance or correction; not an answer yet.' : 'Saved. Pending review; saving does not mark the question answered.'
        await refresh().catch(() => { status.textContent = 'Saved. Review updates are unavailable; reload later to see the receipt.' })
      } catch (error) { status.textContent = `${error.message}. Your text and retry ID are kept.` }
      finally { button.disabled = !acceptingFeedback }
    })
  }
}

function applyFilters() {
  const questions = allQuestions()
  const visible = questions.filter(matchesFilters)
  if (!visible.some(q => q.id === selectedId)) selectedId = visible[0]?.id
  const queue = filters.state.has('proposed')
  $('#review-queue').setAttribute('aria-pressed', String(queue))
  $('#proposal-count').textContent = questions.reduce((n, q) => n + queuedFor(q).length, 0)
  $('#list-title').textContent = queue ? 'SME review queue' : 'Questions'
  $('#empty h3').textContent = queue ? 'No proposals awaiting your review' : 'No questions match'
  for (const state of ['open', 'answered', 'deferred']) $(`#${state}-count`).textContent = questions.filter(q => q.status === state).length
  $('#progress').max = questions.length || 1
  $('#progress').value = questions.filter(q => q.status === 'answered').length
  $('#progress-label').textContent = `${Math.round($('#progress').value / $('#progress').max * 100)}% answered`
  for (const input of document.querySelectorAll('[data-filter]')) {
    input.checked = filters[input.dataset.filter].has(input.value)
    input.parentElement.querySelector('.count').textContent = questions.filter(q => matchesGroup(q, input.dataset.filter, input.value)).length
  }
  for (const q of questions) {
    document.getElementById(`question-${q.id}`).hidden = q.id !== selectedId
    const entry = document.querySelector(`[data-entry="${q.id}"]`)
    entry.hidden = !visible.some(v => v.id === q.id)
    entry.querySelector('a').setAttribute('aria-current', String(q.id === selectedId))
    const pending = pendingFor(q.id)
    const proposals = queuedFor(q).length
    entry.querySelector('.pending').hidden = !pending && !proposals
    entry.querySelector('.pending').textContent = proposals ? `${proposals} proposed · awaiting SME` : `${pending} ${pending === 1 ? 'response needs' : 'responses need'} review`
  }
  for (const r of model.requirements) document.getElementById(`requirement-${r.id}`).hidden = !r.questions.some(q => q.id === selectedId)
  $('#empty').hidden = visible.length > 0
  $('#no-selection').hidden = Boolean(selectedId)
  $('#filter-status').textContent = `${visible.length} of ${questions.length} questions · Revision ${model.revision}`
  const active = Object.entries(filters).flatMap(([group, values]) => [...values].map(value => `<button class="secondary" data-remove="${group}" data-value="${esc(value)}" aria-label="Remove ${esc(filterLabel(group, value))} filter">${esc(filterLabel(group, value))} ×</button>`))
  if ($('#search').value) active.push(`<button class="secondary" data-remove="search" aria-label="Remove search filter">Search: ${esc($('#search').value)} ×</button>`)
  $('#filter-count').textContent = active.length
  const chips = active.join('') || '<p class="muted">No active filters</p>'
  if ($('#active-filters').innerHTML !== chips) $('#active-filters').innerHTML = chips
  showAttention(visible)
}

function showAttention(visible) {
  const pending = feedback.filter(row => !reviews.some(r => r.feedback_id === row.id))
  const counts = { waiting: 0, clarification: 0, conflict: 0 }
  const items = []
  for (const q of allQuestions()) {
    const unreviewed = pending.filter(row => row.question === q.id).length
    const attention = attentionFor(q)
    const label = attention ? `Next action: ${attention.next_action}` : ''
    const note = [unreviewed ? `${unreviewed} ${unreviewed === 1 ? 'response needs' : 'responses need'} review. Review contact: ${model.setup?.reviewer || 'the reviewer'}` : '', label].filter(Boolean).join(' ')
    const box = document.querySelector(`[data-attention="${q.id}"]`)
    box.textContent = note
    box.hidden = !note
    if (visible.some(v => v.id === q.id)) {
      if (attention) counts[attention.state]++
      const authority = attention?.state === 'conflict' ? ` Who decides: ${model.setup?.decision_maker || 'Ask the questionnaire owner.'}` : ''
      if (note) items.push(`<p><a href="#question-${q.id}">${esc(q.title)}</a><br>${esc(note + authority)}</p>`)
    }
  }
  const pendingCount = pending.filter(row => visible.some(q => q.id === row.question)).length
  const summary = Object.entries({ pending: pendingCount, ...counts }).map(([state, count]) => `<div class="attention-count"><span class="symbol" data-tone="${state}" aria-hidden="true">${symbols[state]}</span><strong>${count}</strong><small>${statusLabels[state]} · ${state === 'pending' ? 'responses' : 'questions'}</small></div>`).join('')
  if ($('#attention-counts').innerHTML !== summary) $('#attention-counts').innerHTML = summary
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
  const question = target.closest('.question') || target.querySelector('.question')
  if (question) {
    selectedId = question.id.slice('question-'.length)
    if (!matchesFilters(allQuestions().find(q => q.id === selectedId))) clearFilters()
    applyFilters()
    $('#workspace').dataset.view = 'detail'
  }
  for (let node = target; node; node = node.parentElement) if (node.tagName === 'DETAILS') node.open = true
  const scrollTarget = !desktop.matches && question && !id.startsWith('feedback-') ? $('.question-detail') : target
  const top = scrollTarget.getBoundingClientRect().top
  if (!desktop.matches || id.startsWith('feedback-') || top < 0 || top > innerHeight / 2) scrollTarget.scrollIntoView({ block: 'start' })
  const focusTarget = question && target === question ? question.querySelector('h2') : target
  focusTarget.setAttribute('tabindex', '-1')
  focusTarget.focus({ preventScroll: true })
}

function showFeedback(rows) {
  for (const box of document.querySelectorAll('[data-responses]')) {
    const responses = rows.filter(row => row.question === box.dataset.responses)
    const content = `<h3>Previous feedback (${responses.length})</h3>` + (responses.length ? responses.map(row => {
      const review = reviews.find(r => r.feedback_id === row.id)
      const state = review ? `Reviewed: ${review.summary}` : row.receipt ? 'Reviewer notified. Pending review.' : `Saved. Pending delivery to reviewer${row.attempts ? ` (${row.attempts} attempts)` : ''}.`
      const source = row.context?.proposal_id ? `<p><a href="#proposal-${row.context.proposal_id}">Original proposal</a></p>` : row.kind === 'adopt' ? `<p class="muted">Recommendation adopted from revision ${esc(row.context.revision)}</p>` : ''
      return `<div class="response" id="feedback-${row.id}"><strong>${esc(row.name)} · ${esc(row.kind)}</strong><p>${esc(row.message)}</p>${source}<small>${esc(row.created_at)} · self-reported name</small><p class="review-note">${esc(state)}</p></div>`
    }).join('') : '<p class="muted">No feedback yet.</p>')
    if (box.innerHTML !== content) box.innerHTML = content
  }
}

function showProposals() {
  for (const q of allQuestions()) {
    const box = document.querySelector(`[data-proposals="${q.id}"]`)
    for (const proposal of feedback.filter(f => f.question === q.id && ['propose', 'adopt'].includes(f.kind))) {
      let card = document.getElementById(`proposal-${proposal.id}`)
      const key = `proposal:${proposal.id}`
      if (!card) {
        card = document.createElement('section')
        card.id = `proposal-${proposal.id}`
        card.className = 'proposal'
        card.dataset.id = proposal.id
        card.innerHTML = `<strong class="proposal-label"></strong><p class="proposal-text">${esc(proposal.message)}</p><p class="muted">Proposed by ${esc(proposal.name)}${proposal.kind === 'adopt' ? ' · recommendation adopted' : ''} · revision ${esc(proposal.context?.revision ?? 'not recorded')}</p><p class="proposal-state" role="status"></p><div class="proposal-actions"><button type="button" data-decision="accept">Accept and next</button><button type="button" class="secondary" data-correct>Correct proposal</button></div><div class="correction" hidden><label>Corrected answer<textarea maxlength="3000" rows="3"></textarea></label><p class="muted">Accepting saves your corrected wording and keeps the original proposal.</p><div class="proposal-actions"><button type="button" data-decision="correct">Accept corrected answer</button><button type="button" class="secondary" data-cancel>Cancel</button></div></div><p class="status" role="status"></p>`
        const editor = card.querySelector('.correction')
        editor.hidden = !drafts[key]?.editing
        card.querySelector('textarea').value = drafts[key]?.message ?? proposal.message
        card.querySelector('textarea').addEventListener('input', event => {
          drafts[key] = { ...drafts[key], editing: true, message: event.target.value }
          saveDrafts()
        })
        box.append(card)
      }
      const resolved = !proposalsFor(q).some(p => p.id === proposal.id)
      const selected = q.answer?.proposal_id === proposal.id
      const acceptance = feedback.find(f => f.id === q.answer?.acceptance_id)
      const decisions = decisionsFor(proposal)
      const pending = decisions.some(d => !reviews.some(r => r.feedback_id === d.id))
      card.dataset.tone = resolved ? 'history' : 'proposed'
      card.querySelector('.proposal-label').textContent = selected ? acceptance.kind === 'correct' ? 'Original proposal · accepted with corrections' : 'Original proposal · accepted unchanged' : resolved ? 'Earlier proposal · not selected' : 'Proposed answer · not settled'
      card.querySelector('.proposal-state').textContent = selected ? `${acceptance.kind === 'correct' ? 'Corrected and accepted' : 'Accepted'} by ${acceptance.name}. See the accepted answer above.` : resolved ? 'Another proposal was accepted. The original remains in the history.' : pending ? 'Acceptance saved. Awaiting reviewer publication; not settled yet.' : q.status === 'answered' ? 'Challenges the current answer. Review does not silently replace it.' : 'Awaiting SME acceptance or correction.'
      card.querySelector('.proposal-actions').hidden = resolved || pending || !acceptingFeedback || Boolean(drafts[key]?.editing)
      for (const button of card.querySelectorAll('[data-decision], [data-correct]')) button.disabled = resolved || pending || !acceptingFeedback
    }
  }
}

async function saveDecision(card, kind) {
  const proposal = feedback.find(f => f.id === card.dataset.id)
  const status = card.querySelector('.status')
  const key = `proposal:${proposal.id}`
  const name = $('#reviewer-name').value.trim()
  if (!name) { status.textContent = 'Enter your name in “Reviewing as” before accepting.'; $('#reviewer-name').focus(); return }
  const message = kind === 'accept' ? proposal.message : card.querySelector('textarea').value
  if (!message.trim()) { status.textContent = 'Enter the corrected answer before accepting.'; card.querySelector('textarea').focus(); return }
  const payload = { question: proposal.question, name, kind, message, context: { revision: model.revision, proposal_id: proposal.id } }
  const fingerprint = JSON.stringify(payload)
  drafts[key] ||= {}
  if (drafts[key].pending?.fingerprint !== fingerprint) drafts[key].pending = { fingerprint, id: crypto.randomUUID() }
  saveDrafts()
  for (const button of card.querySelectorAll('button')) button.disabled = true
  status.textContent = 'Saving acceptance…'
  let saved = false
  try {
    const response = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, id: drafts[key].pending.id }) })
    const result = await response.json()
    if (!response.ok) throw new Error(result.error || 'Save failed')
    saved = true
    status.textContent = 'Acceptance saved. Pending reviewer publication.'
    $('#proposal-status').textContent = 'Acceptance saved. The reviewer still needs to publish the settled answer.'
    await refresh()
    delete drafts[key]
    saveDrafts()
    card.querySelector('.correction').hidden = true
    const next = allQuestions().find(q => queuedFor(q).length && matchesFilters(q))
    if (next) { history.pushState(null, '', `#question-${next.id}`); reveal() }
    else { $('#proposal-status').textContent += ' No more proposals in this queue.'; $('#review-queue').focus() }
  } catch (error) { status.textContent = saved ? 'Acceptance saved, but updates are unavailable. Your retry ID is kept; retrying will not save a duplicate.' : `${error.message}. Your draft and retry ID are kept.` }
  finally {
    for (const button of card.querySelectorAll('button')) button.disabled = !acceptingFeedback
    showProposals()
  }
}

async function refresh() {
  const response = await fetch('/api/state', { cache: 'no-store' })
  if (!response.ok) throw new Error('Could not load review updates')
  const state = await response.json()
  feedback = state.feedback
  reviews = state.model.reviews
  acceptingFeedback = state.model.state !== 'closed'
  if (!model) {
    model = state.model
    try { drafts = JSON.parse(sessionStorage.getItem(draftKey()) || '{}') } catch { drafts = {} }
    for (const [key, draft] of Object.entries(drafts)) {
      const saved = feedback.find(f => f.id === draft?.pending?.id)
      if (!saved) continue
      if (key.startsWith('proposal:')) delete drafts[key]
      else {
        delete draft.pending
        if (draft.message === saved.message) draft.message = ''
        if (draft.kind === 'adopt') draft.kind = 'answer'
      }
    }
    saveDrafts()
    render()
    $('#filters-panel').open = desktop.matches
  }
  $('#delivery-mode').textContent = !acceptingFeedback ? `Closed. New feedback is disabled. ${state.model.closure.reason} Deferred questions are not answered; existing unreviewed feedback remains marked.` : state.mode === 'automatic' ? 'Automatic review. Feedback is saved before the reviewer is notified. Each response shows its delivery and review receipts.' : 'Manual review. Your feedback is saved here. Send this page to the reviewer to get it reviewed.'
  if (!acceptingFeedback) for (const button of document.querySelectorAll('form button[type="submit"]')) button.disabled = true
  for (const notice of document.querySelectorAll('[data-save-notice]')) notice.textContent = !acceptingFeedback ? 'This review is closed. Unsent drafts remain in this tab; copy them before leaving.' : state.mode === 'automatic' ? 'Saving adds your feedback to this page and queues it for review. Saving does not mark the question answered.' : 'Saving adds your feedback to this page. Share the page with the reviewer to request review.'
  $('#update').hidden = state.model.revision === model.revision
  showFeedback(state.feedback)
  showProposals()
  applyFilters()
}

document.addEventListener('click', event => {
  const button = event.target.closest('button')
  if (button?.dataset.adopt) {
    const q = allQuestions().find(q => q.id === button.dataset.adopt)
    const form = document.querySelector(`form[data-question="${q.id}"]`)
    form.elements.kind.value = 'adopt'
    form.elements.message.value = q.request.recommendation
    form.dispatchEvent(new Event('input'))
    form.scrollIntoView({ block: 'center' })
    form.elements.person.focus()
  }
  const card = button?.closest('.proposal')
  if (card && button.hasAttribute('data-correct')) {
    const key = `proposal:${card.dataset.id}`
    drafts[key] = { ...drafts[key], editing: true, message: card.querySelector('textarea').value }
    saveDrafts()
    card.querySelector('.correction').hidden = false
    card.querySelector('.proposal-actions').hidden = true
    card.querySelector('textarea').focus()
    card.querySelector('.correction').scrollIntoView({ block: 'nearest' })
  }
  if (card && button.hasAttribute('data-cancel')) {
    delete drafts[`proposal:${card.dataset.id}`]
    saveDrafts()
    card.querySelector('textarea').value = feedback.find(f => f.id === card.dataset.id).message
    card.querySelector('.correction').hidden = true
    showProposals()
    card.querySelector('[data-correct]').focus()
  }
  if (card && button.dataset.decision) saveDecision(card, button.dataset.decision)
  if (button?.dataset.clear !== undefined) clearFilters()
  if (button?.dataset.remove) {
    if (button.dataset.remove === 'search') $('#search').value = ''
    else filters[button.dataset.remove].delete(button.dataset.value)
    applyFilters()
    $('#reset').focus()
  }
  const link = event.target.closest('a[href^="#"]')
  if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); history.pushState(null, '', link.getAttribute('href')); reveal() }
})
document.addEventListener('change', event => {
  const input = event.target.closest('[data-filter]')
  if (input) { filters[input.dataset.filter][input.checked ? 'add' : 'delete'](input.value); applyFilters() }
})
$('#search').addEventListener('input', applyFilters)
$('#reviewer-name').addEventListener('input', () => { drafts.reviewerName = $('#reviewer-name').value; saveDrafts() })
$('#review-queue').addEventListener('click', () => {
  const wasQueued = filters.state.has('proposed')
  clearFilters()
  if (!wasQueued) filters.state.add('proposed')
  applyFilters()
  $('#workspace').dataset.view = 'list'
  $('#list-title').focus()
})
$('#reset').addEventListener('click', clearFilters)
$('#sort').addEventListener('change', () => {
  const questions = allQuestions()
  const priorities = [...new Set(questions.map(q => q.priority))]
  questions.sort((a, b) => $('#sort').value === 'title' ? a.title.localeCompare(b.title) : priorities.indexOf(a.priority) - priorities.indexOf(b.priority))
  for (const q of questions) $('#question-nav').append(document.querySelector(`[data-entry="${q.id}"]`))
})
$('#back-to-list').addEventListener('click', () => {
  $('#workspace').dataset.view = 'list'
  history.pushState(null, '', location.pathname + location.search)
  const link = $('#question-nav a[aria-current="true"]') || $('#list-title')
  link.focus()
})
desktop.addEventListener('change', () => { $('#filters-panel').open = desktop.matches })
$('#reload').addEventListener('click', () => { if (saveDrafts()) location.reload() })
window.addEventListener('hashchange', () => { if (location.hash) reveal(); else $('#workspace').dataset.view = 'list' })
refresh().then(reveal).catch(() => { $('#load-status').textContent = 'Could not load this questionnaire. Reload to retry.' })
setInterval(() => { if (model && document.visibilityState === 'visible') refresh().catch(() => { $('#load-status').textContent = 'Updates unavailable. Saved feedback is unaffected; drafts remain in this tab.' }) }, 5000)
