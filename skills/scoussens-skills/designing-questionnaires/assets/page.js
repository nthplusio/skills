let model
let drafts = {}
let feedback = []
let reviews = []
let pendingProposals = {}
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
  return feedback.filter(f => f.question === q.id && ['propose', 'adopt'].includes(f.kind) && !q.proposal_outcomes?.[f.id] && (!acceptance || f.created_at > acceptance.created_at) && !decisionsFor(f).some(d => d.kind === 'deny' && reviews.some(r => r.feedback_id === d.id)))
}
const decisionsFor = proposal => feedback.filter(f => f.context?.proposal_id === proposal.id && ['accept', 'correct', 'deny'].includes(f.kind))
const queuedFor = q => feedback.filter(f => pendingProposals[q.id]?.includes(f.id))
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
      if (payload.kind === 'propose' && payload.message === question.request?.recommendation) payload.kind = 'adopt'
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
  $('#empty p').textContent = queue ? 'Decisions take effect when saved. Clear the filter to see answers and history.' : 'Remove a filter or try another search.'
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
      const state = review ? `${review.method === 'host_recorded' ? 'Recorded' : 'Reviewed'}: ${review.summary}` : row.receipt ? 'Reviewer notified. Pending review.' : `Saved. Pending delivery to reviewer${row.attempts ? ` (${row.attempts} attempts)` : ''}.`
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
        card.innerHTML = `<strong class="proposal-label"></strong><p class="proposal-text">${esc(proposal.message)}</p><p class="muted">Proposed by ${esc(proposal.name)}${proposal.kind === 'adopt' ? ' · recommendation adopted' : ''} · revision ${esc(proposal.context?.revision ?? 'not recorded')}</p><p class="proposal-state" role="status"></p><div class="proposal-actions"><button type="button" data-decision="accept">Accept and next</button><button type="button" class="secondary" data-edit="correct">Correct and accept</button><button type="button" class="secondary" data-edit="deny">Deny proposal</button></div><div class="correction" hidden><label><span data-editor-label>Corrected answer</span><textarea maxlength="3000" rows="3"></textarea></label><p class="muted" data-editor-hint></p><div class="proposal-actions"><button type="button" data-decision="correct" data-editor-submit>Accept corrected answer</button><button type="button" class="secondary" data-cancel>Cancel</button></div></div><div class="replacement review-note" hidden><strong>Replace the current answer?</strong><p data-current-answer></p><p data-replacement-answer></p><div class="proposal-actions"><button type="button" data-confirm-replacement>Confirm replacement</button><button type="button" class="secondary" data-cancel>Cancel</button></div></div><p class="status" role="status"></p>`
        const editor = card.querySelector('.correction')
        editor.hidden = !drafts[key]?.editing
        card.querySelector('textarea').value = drafts[key]?.message ?? proposal.message
        card.querySelector('textarea').addEventListener('input', event => {
          drafts[key] = { ...drafts[key], message: event.target.value }
          saveDrafts()
        })
        box.append(card)
      }
      const resolved = !proposalsFor(q).some(p => p.id === proposal.id)
      const outcome = q.proposal_outcomes?.[proposal.id]
      const selected = q.answer?.proposal_id === proposal.id
      const acceptance = feedback.find(f => f.id === (selected ? q.answer?.acceptance_id : outcome?.decision_id))
      const decisions = decisionsFor(proposal)
      const denial = decisions.find(d => d.kind === 'deny' && reviews.some(r => r.feedback_id === d.id))
      const pending = decisions.find(d => !reviews.some(r => r.feedback_id === d.id))
      if (pending) card.querySelector('.status').textContent = ''
      const denying = drafts[key]?.editing === 'deny'
      const recovered = resolved && Boolean(drafts[key]?.editing || drafts[key]?.replacement)
      card.querySelector('[data-editor-label]').textContent = recovered ? 'Unsent draft (not submitted)' : denying ? 'Feedback (optional)' : 'Corrected answer'
      card.querySelector('textarea').readOnly = recovered
      card.querySelector('[data-editor-hint]').textContent = recovered ? 'Another decision settled this proposal. Copy your draft before dismissing it. To suggest different wording, submit a fresh proposal below.' : denying ? 'Deny only this proposal, with or without feedback. Other proposals stay available; this does not answer the question.' : 'Accepting saves your corrected wording and keeps the original proposal.'
      card.querySelector('[data-editor-submit]').dataset.decision = denying ? 'deny' : 'correct'
      card.querySelector('[data-editor-submit]').textContent = denying ? 'Deny and next' : 'Accept corrected answer'
      card.querySelector('[data-editor-submit]').hidden = recovered
      card.querySelector('.correction [data-cancel]').textContent = recovered ? 'Dismiss draft' : 'Cancel'
      card.querySelector('.correction').hidden = !recovered && (resolved || Boolean(pending) || !drafts[key]?.editing)
      card.querySelector('.replacement').hidden = resolved || !drafts[key]?.replacement
      if (!resolved && drafts[key]?.replacement) {
        card.querySelector('[data-current-answer]').textContent = `Current answer: ${q.answer?.text || 'No current answer'}`
        card.querySelector('[data-replacement-answer]').textContent = `New answer: ${drafts[key].replacement.message}`
        card.querySelector('.correction').hidden = true
      }
      card.querySelector('[data-decision="accept"]').textContent = q.answer ? 'Replace current answer' : 'Accept and next'
      card.dataset.tone = resolved ? 'history' : 'proposed'
      card.querySelector('.proposal-label').textContent = denial ? 'Denied proposal' : selected || outcome?.state === 'accepted' ? acceptance.kind === 'correct' ? 'Original proposal · accepted with corrections' : 'Original proposal · accepted unchanged' : pending ? 'Earlier decision · needs reviewer reconciliation' : resolved ? 'Earlier proposal · not selected' : q.answer ? 'Proposed replacement' : 'Proposed answer · awaiting decision'
      card.querySelector('.proposal-state').textContent = denial ? `Denied by ${denial.name}. ${denial.message.trim() || 'No feedback provided.'}` : selected ? `${acceptance.kind === 'correct' ? 'Corrected and accepted' : 'Accepted'} by ${acceptance.name}. See the accepted answer above.` : outcome?.state === 'accepted' ? `Previously accepted by ${acceptance.name}. The decision is preserved in history.` : resolved ? 'Another proposal was accepted. The original remains in the history.' : pending ? 'This decision predates immediate decisions. The reviewer must reconcile it; it has not been applied automatically.' : q.status === 'answered' ? 'The current answer stays unchanged unless you confirm its replacement.' : 'Awaiting SME acceptance, correction or denial.'
      card.querySelector('.proposal-actions').hidden = resolved || pending || !acceptingFeedback || Boolean(drafts[key]?.editing || drafts[key]?.replacement)
      for (const button of card.querySelectorAll('[data-decision], [data-edit]')) button.disabled = resolved || Boolean(pending) || !acceptingFeedback
    }
  }
}

async function saveDecision(card, kind, replace = false) {
  const proposal = feedback.find(f => f.id === card.dataset.id)
  const status = card.querySelector('.status')
  const key = `proposal:${proposal.id}`
  const name = $('#reviewer-name').value.trim()
  if (!name) { status.textContent = 'Enter your name in “Reviewing as” before saving a decision.'; $('#reviewer-name').focus(); return }
  const message = kind === 'accept' ? proposal.message : card.querySelector('textarea').value
  if (kind !== 'deny' && !message.trim()) { status.textContent = 'Enter the corrected answer before accepting.'; card.querySelector('textarea').focus(); return }
  const decisionLabel = kind === 'deny' ? 'Denial' : 'Acceptance'
  const question = allQuestions().find(q => q.id === proposal.question)
  if (kind !== 'deny' && question.answer && !replace) {
    drafts[key] = { ...drafts[key], replacement: { kind, message } }
    saveDrafts()
    showProposals()
    card.querySelector('[data-confirm-replacement]').focus()
    return
  }
  const payload = { question: proposal.question, name, kind, message, context: { revision: model.revision, proposal_id: proposal.id } }
  if (replace) payload.context.replace = true
  const fingerprint = JSON.stringify(payload)
  drafts[key] ||= {}
  if (drafts[key].pending?.fingerprint !== fingerprint) drafts[key].pending = { fingerprint, id: crypto.randomUUID() }
  saveDrafts()
  for (const button of card.querySelectorAll('button')) button.disabled = true
  status.textContent = `Saving ${decisionLabel.toLowerCase()}…`
  let saved = false
  try {
    const response = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, id: drafts[key].pending.id }) })
    const result = await response.json()
    if (!response.ok) throw new Error(result.error || 'Save failed')
    saved = true
    $('#proposal-status').textContent = kind === 'deny' ? 'Proposal denied. Other proposals and the current answer are unchanged.' : replace ? 'Answer replaced. The previous answer is preserved in history.' : 'Accepted. This question is answered.'
    await refresh(true)
    delete drafts[key]
    saveDrafts()
    const next = allQuestions().find(q => queuedFor(q).length && matchesFilters(q))
    if (next) {
      history.pushState(null, '', `#question-${next.id}`)
      reveal()
      const nextCard = document.getElementById(`proposal-${queuedFor(next)[0].id}`)
      nextCard.scrollIntoView({ block: 'nearest' })
      nextCard.querySelector('button').focus({ preventScroll: true })
    }
    else {
      $('#proposal-status').textContent += ' No more proposals in this queue.'
      if (filters.state.has('proposed')) { filters.state.delete('proposed'); applyFilters(); history.pushState(null, '', `#question-${proposal.question}`); reveal() }
      $('#review-queue').focus()
    }
  } catch (error) { status.textContent = saved ? `${decisionLabel} saved, but updates are unavailable. Your retry ID is kept; retrying will not save a duplicate.` : `${error.message}. Your draft and retry ID are kept.` }
  finally {
    for (const button of card.querySelectorAll('button')) button.disabled = !acceptingFeedback
    showProposals()
  }
}

async function refresh(adopt = false) {
  const response = await fetch('/api/state', { cache: 'no-store' })
  if (!response.ok) throw new Error('Could not load review updates')
  const state = await response.json()
  if (model && state.model.revision < model.revision) return
  acceptingFeedback = state.model.state !== 'closed'
  if (model && state.model.revision !== model.revision && !adopt) {
    $('#update').hidden = false
    if (!acceptingFeedback) {
      $('#delivery-mode').textContent = `Closed. New feedback is disabled. ${state.model.closure.reason}`
      for (const button of document.querySelectorAll('form button[type="submit"], .proposal button')) button.disabled = true
    }
    return
  }
  feedback = state.feedback
  reviews = state.model.reviews
  pendingProposals = state.pending_proposals
  const initial = !model
  if (initial || adopt) {
    model = state.model
    if (initial) { try { drafts = JSON.parse(sessionStorage.getItem(draftKey()) || '{}') } catch { drafts = {} } }
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
  $('#delivery-mode').textContent = !acceptingFeedback ? `Closed. New feedback is disabled. ${state.model.closure.reason} Deferred questions are not answered; existing unreviewed feedback remains marked.` : `SME decisions take effect immediately. ${state.mode === 'automatic' ? 'Reviewer notifications are automatic.' : 'Share this page with the reviewer for other feedback.'}`
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
    form.elements.kind.value = 'propose'
    form.elements.message.value = q.request.recommendation
    form.dispatchEvent(new Event('input'))
    form.scrollIntoView({ block: 'center' })
    form.elements.person.focus()
  }
  const card = button?.closest('.proposal')
  if (card && button.dataset.edit) {
    const key = `proposal:${card.dataset.id}`
    const message = button.dataset.edit === 'deny' ? '' : feedback.find(f => f.id === card.dataset.id).message
    drafts[key] = { ...drafts[key], editing: button.dataset.edit, message }
    card.querySelector('textarea').value = message
    saveDrafts()
    showProposals()
    card.querySelector('textarea').focus()
    card.querySelector('.correction').scrollIntoView({ block: 'nearest' })
  }
  if (card && button.hasAttribute('data-cancel')) {
    delete drafts[`proposal:${card.dataset.id}`]
    saveDrafts()
    card.querySelector('textarea').value = feedback.find(f => f.id === card.dataset.id).message
    card.querySelector('.correction').hidden = true
    showProposals()
    card.tabIndex = -1
    const focusTarget = card.querySelector('.proposal-actions').hidden ? card : card.querySelector('[data-edit="correct"]')
    focusTarget.focus()
  }
  if (card && button.hasAttribute('data-confirm-replacement')) {
    const replacement = drafts[`proposal:${card.dataset.id}`]?.replacement
    if (replacement) saveDecision(card, replacement.kind, true)
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
    const next = allQuestions().find(q => queuedFor(q).length)
    if (!wasQueued && next) {
      history.pushState(null, '', `#question-${next.id}`)
      reveal()
      const card = document.getElementById(`proposal-${queuedFor(next)[0].id}`)
      card.scrollIntoView({ block: 'nearest' })
      card.querySelector('button').focus({ preventScroll: true })
    } else { $('#workspace').dataset.view = 'list'; $('#list-title').focus() }
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
