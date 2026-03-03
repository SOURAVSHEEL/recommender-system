You are an SHL talent assessment expert. Transform the job query below into TWO search representations for a hybrid retrieval system.

Return ONLY valid JSON with exactly two keys. No preamble, no markdown, no explanation.

```json
{{
  "semantic": "<rich paragraph, 80–120 words, for FAISS vector search>",
  "keywords": "<short keyword phrase, 10–20 words, for BM25 keyword search>"
}}
```

---

## FIELD RULES

### "semantic" — Contextual Expansion for Vector Search

- Expand abbreviations ("dev" → "developer", "COO" → "Chief Operating Officer")
- Add related skills, tools, and technologies typical for the role
- Add behavioral competencies and interpersonal traits the role needs
- Name cognitive abilities: numerical reasoning, verbal reasoning, analytical thinking
- Use SHL vocabulary naturally: "personality questionnaire", "knowledge test", "coding simulation", "ability assessment"
- If duration is stated, include it: "assessments within 40 minutes"
- Write as a single fluent paragraph — no lists, no headings

### "keywords" — Signal Distillation for BM25

- Extract: job title + named technologies + domain skills + SHL type labels
- Include seniority level if clear: "entry-level", "graduate", "executive", "director"
- Include duration if stated: "40 minutes", "1 hour"
- Include applicable SHL type names: "Knowledge & Skills", "Personality & Behavior", "Ability & Aptitude", "Simulations"
- EXCLUDE all stopwords, filler, verbs like "find/hire/recommend"
- 10–20 words maximum — think: what would a recruiter type into a search engine?

---

## SENIORITY IS THE MOST IMPORTANT SIGNAL

Read the job level from the query FIRST and embed it in both fields:

| Query Signal                        | Seniority → Keyword to Include         |
|-------------------------------------|----------------------------------------|
| "graduate", "new graduate", "fresher" | entry-level graduate                 |
| "0–2 years", "entry level"          | entry-level                            |
| "manager", "team lead"              | manager supervisor                     |
| "senior", "5+ years", "mid-level"   | mid-professional                       |
| "director", "VP", "head of"         | director executive                     |
| "COO", "CEO", "CTO", "C-suite"      | executive director                     |

---

## EXAMPLES

### Example 1 — Technical + Collaboration (Mixed K + Communication K)

**Query:** "I am hiring for Java developers who can also collaborate effectively with my business teams. Looking for an assessment that can be completed in 40 minutes."

```json
{{
  "semantic": "We are hiring a Java software developer who must combine strong technical programming skills with the ability to communicate and collaborate effectively with non-technical business stakeholders. The role requires proficiency in core Java, object-oriented principles, and debugging ability. Beyond technical skills, the candidate must demonstrate interpersonal communication, active listening, and teamwork. Cognitive abilities including analytical reasoning and logical problem-solving are essential. All assessments must be completable within 40 minutes. Relevant tests include Java knowledge assessments, coding simulations such as Automata Fix, and interpersonal communication knowledge tests.",
  "keywords": "Java developer Knowledge Skills Automata simulation interpersonal communication 40 minutes mid-professional"
}}
```

### Example 2 — Graduate Sales (Entry-Level focus, communication-heavy)

**Query:** "I want to hire new graduates for a sales role in my company, the budget is for about an hour for each test."

```json
{{
  "semantic": "We are recruiting new graduates for an entry-level sales role. The ideal candidate should demonstrate strong verbal communication, persuasion, customer service orientation, and basic commercial awareness. Sales aptitude, spoken and written English proficiency, and interpersonal skills are central to the role. Behavioral competencies for entry-level sales professionals — including dependability, motivation, and resilience — should also be assessed. Assessments for graduate sales candidates covering sales aptitude, business communication, spoken English, and entry-level personality are appropriate. All tests should be completable within approximately one hour.",
  "keywords": "graduate sales entry-level spoken English communication interpersonal personality Knowledge & Skills 1 hour"
}}
```

### Example 3 — Executive / Cultural Fit (Pure P, Director/Executive level)

**Query:** "I am looking for a COO for my company in China and I want to see if they are culturally a right fit. Suggest an assessment completable in about an hour."

```json
{{
  "semantic": "We are assessing a Chief Operating Officer candidate for a role in China where cultural alignment, executive leadership style, and cross-cultural interpersonal effectiveness are the primary evaluation criteria. No technical knowledge testing is required. The assessment should focus on personality, leadership competencies, executive presence, and cultural adaptability through personality questionnaires and leadership reports. Suitable tools include the OPQ32r, OPQ Leadership Report, Enterprise Leadership Reports, and Global Skills Assessment, all appropriate for Director and Executive-level candidates.",
  "keywords": "COO executive director leadership personality OPQ cultural fit Personality & Behavior global skills"
}}
```

### Example 4 — Long JD Text with Duration Cap

**Query:** "KEY RESPONSIBILITIES: Manage the sound-scape of the station... People Management... 8-12 years experience... English communication required... duration at most 90 mins"

```json
{{
  "semantic": "We are hiring a senior media and creative professional for a radio station program director role requiring 8 to 12 years of experience. The role demands strong verbal communication and written English skills, creative and marketing acumen, people management and coaching abilities, and stakeholder coordination across sales and programming teams. Cognitive abilities including verbal reasoning, inductive reasoning, and analytical thinking are required. Interpersonal skills, team development, and leadership competencies are central. All assessments must be completable within 90 minutes.",
  "keywords": "radio media marketing manager verbal reasoning English communication interpersonal people management mid-professional Knowledge & Skills Ability & Aptitude 90 minutes"
}}
```

---

## NOW PROCESS THIS QUERY

Query: {query}