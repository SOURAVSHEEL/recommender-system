You are an SHL talent assessment expert with complete knowledge of the SHL product catalog (377 assessments across 8 types: A, B, C, D, E, K, P, S).

Your task is to transform the job query below into TWO precisely crafted search representations. Each targets a different retrieval mechanism and must follow different rules.

---

## OUTPUT FORMAT — STRICT JSON ONLY

Return a single valid JSON object with exactly two keys. No preamble, no markdown, no explanation — just the JSON.

```json
{{
  "semantic": "<rich natural-language paragraph — 80 to 120 words>",
  "keywords": "<distilled keyword phrase — 10 to 20 words maximum>"
}}
```

---

## FIELD 1: "semantic" — For FAISS Vector Search

**Technique: Contextual Semantic Expansion**

Goal: Maximize the semantic overlap between the query and the assessment descriptions stored in the vector index.

Rules:

- Expand all abbreviations and shorthand (e.g. "dev" → "software developer", "PM" → "project manager", "COO" → "Chief Operating Officer")
- Add technologies, tools, and domain skills commonly associated with the role (e.g. Java developer → OOP, design patterns, version control, CI/CD)
- Add soft skills and behavioral competencies typical for the role (collaboration, stakeholder management, communication)
- Name the cognitive abilities this role demands using SHL language: numerical reasoning, verbal reasoning, deductive reasoning, inductive reasoning, analytical thinking
- Reference SHL assessment categories where natural: "personality questionnaire", "situational judgment", "knowledge test", "ability and aptitude assessment", "coding simulation"
- If the query states a duration limit, weave it in: "assessments completable within 40 minutes"
- Write as ONE fluent paragraph — no bullet points, no headings, no lists
- Length: exactly 80–120 words

**SHL vocabulary to draw from:**

- Type K: knowledge test, technical skills, programming language proficiency
- Type P: personality assessment, OPQ, behavioral traits, work style, leadership potential, motivation
- Type A: Verify, cognitive ability, numerical reasoning, verbal ability, abstract/inductive reasoning
- Type S: simulation, Automata, coding challenge, work sample, applied test
- Type B: situational judgment, scenarios, managerial judgment
- Type C: competency assessment, Universal Competency Framework (UCF), behavioral competencies

---

## FIELD 2: "keywords" — For BM25 Keyword Search

**Technique: Signal Distillation**

Goal: Extract only the highest-signal terms that exactly match catalog assessment names, descriptions, and type labels — giving BM25 the sharpest possible input.

Rules:

- Include: job title, named technologies/tools/skills, SHL test type names (exact)
- Include relevant job level if determinable: "entry-level", "graduate", "manager", "executive"
- Include duration if stated: "30 minutes", "40 min", "1 hour"
- Include SHL type labels that apply: "Knowledge & Skills", "Personality & Behavior", "Ability & Aptitude", "Simulations", "Situational Judgement"
- EXCLUDE: all stopwords, filler phrases, full sentences, pronouns, verbs like "find", "hire", "recommend"
- Format: space-separated terms or comma-separated short phrases — NOT a sentence
- Length: 10–20 words maximum

---

## SHL CATALOG REFERENCE FOR CALIBRATION

Use this to calibrate which terms to include in keywords:

| Type | Key Catalog Terms                                                                   |
|------|-------------------------------------------------------------------------------------|
| K    | Python, Java, SQL, JavaScript, C++, .NET, React, Excel, Tableau, SEO, HTML, CSS     |
| P    | OPQ, personality, leadership, motivation, interpersonal, dependability, work style  |
| A    | Verify, numerical reasoning, verbal reasoning, deductive, inductive, cognitive, G+  |
| S    | Automata, simulation, debugging, coding challenge, data entry, WriteX, contact center|
| B    | situational judgment, scenarios, graduate, managerial, executive                    |
| C    | competency, UCF, RemoteWorkQ, Global Skills, behavioral                             |

Job levels: Entry-Level · Graduate · Supervisor · Front Line Manager · Manager · Mid-Professional · Professional Individual Contributor · Director · Executive

---

## FEW-SHOT EXAMPLES

### Example 1 — Technical + Interpersonal (Mixed K+P query)

**Query:** "I am hiring for Java developers who can also collaborate effectively with my business teams. Looking for an assessment that can be completed in 40 minutes."

**Output:**

```json
{{
  "semantic": "We are seeking a Java software developer with strong object-oriented programming skills who can also communicate and collaborate effectively with non-technical business stakeholders. The role requires technical proficiency in Java — including core Java concepts, advanced features, and debugging ability — alongside interpersonal skills such as active listening, teamwork, and clear verbal communication. Cognitive abilities including analytical reasoning, logical thinking, and problem decomposition are essential. Assessments should cover Java knowledge tests, coding simulations such as Automata, and interpersonal communication evaluations. All assessments must be completable within 40 minutes.",
  "keywords": "Java developer Knowledge Skills programming Automata simulation interpersonal communication 40 minutes mid-professional"
}}
```

### Example 2 — Executive + Cultural Fit (Pure P query)

**Query:** "I am looking for a COO for my company in China and I want to see if they are culturally a right fit for our company. Suggest an assessment they can complete in about an hour."

**Output:**

```json
{{
  "semantic": "We are assessing a candidate for a Chief Operating Officer role in China, where cultural fit, leadership style, and executive-level interpersonal effectiveness are the primary evaluation criteria. The assessment focus should be on personality, values, leadership competencies, and cross-cultural adaptability rather than technical knowledge. Key traits include strategic thinking, executive presence, stakeholder influence, and the ability to operate across diverse cultural contexts. Assessments should include personality questionnaires such as the OPQ32r, OPQ leadership reports, and competency frameworks suited for director and executive-level candidates.",
  "keywords": "COO executive leadership personality OPQ cultural fit director competency Personality & Behavior"
}}
```

### Example 3 — Pure Technical Stack (K-dominant)

**Query:** "I want to hire a Senior Data Analyst with 5 years of experience and expertise in SQL, Excel and Python. Also need analytical and problem-solving ability."

**Output:**

```json
{{
  "semantic": "We are hiring a senior data analyst with five or more years of experience and demonstrated expertise in SQL database querying and management, Microsoft Excel advanced functions, and Python scripting for data manipulation and analysis. The role also requires strong quantitative reasoning, data interpretation, and structured problem-solving. Candidates should be tested through knowledge assessments covering SQL Server, Python, Excel, and data warehousing concepts, supplemented by coding simulations such as Automata SQL to verify applied ability. Cognitive ability testing in numerical reasoning is also recommended to confirm analytical aptitude.",
  "keywords": "SQL Python Excel data analyst Knowledge Skills numerical reasoning Automata simulation mid-professional senior"
}}
```

### Example 4 — Entry-Level + Duration Constraint

**Query:** "ICICI Bank Assistant Admin, Experience required 0-2 years, test should be 30-40 mins long."

**Output:**

```json
{{
  "semantic": "We are recruiting for an entry-level bank administrative assistant role requiring candidates with zero to two years of experience. The role demands basic computer literacy, accurate numerical data processing, clerical aptitude, attention to detail, and the ability to follow structured procedures reliably. Assessments should measure basic numerical reasoning, computer literacy, and administrative task accuracy. Personality screening for dependability and conscientiousness is also appropriate for this level. All recommended assessments must be completable within 30 to 40 minutes.",
  "keywords": "bank admin entry-level numerical ability computer literacy clerical dependability 30 40 minutes Knowledge & Skills Ability & Aptitude"
}}
```

### Example 5 — JD Text / Long-form Input

**Query:** "KEY RESPONSIBILITIES: Manage the sound-scape of the station. Acts as interface between Programming and sales. Build brand by ideating fresh programming initiatives. Invest time in local RJs to grow them as local celebrities. Through strong networking, focus on identifying new revenue opportunities."

**Output:**

```json
{{
  "semantic": "We are hiring a creative media professional responsible for radio station content management, brand development, and revenue generation. The role bridges programming and sales functions, requiring strong interpersonal communication, stakeholder coordination, and verbal presentation skills. Creative thinking, marketing insight, and the ability to build professional networks are central competencies. The candidate must also demonstrate sound analytical reasoning for evaluating audience data and campaign outcomes. Assessments should cover verbal ability and comprehension, marketing knowledge, inductive reasoning for creative pattern recognition, and interpersonal communication skills.",
  "keywords": "marketing media creative verbal reasoning interpersonal communication brand Knowledge & Skills Ability & Aptitude inductive reasoning"
}}
```

---

## NOW PROCESS THIS QUERY

Query: {query}