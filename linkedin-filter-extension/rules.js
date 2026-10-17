/*
 * Pure extraction and filtering helpers for the local LinkedIn Lens extension.
 * This file deliberately has no Chrome API dependency so its behaviour can be
 * tested under Node and reused by content/background scripts.
 */
(function attachJobFilterRules(global) {
  "use strict";

  const SENIORITY_LEVELS = [
    "internship", "entry", "associate", "mid", "senior", "staff", "director", "executive",
  ];

  const SENIORITY_PATTERNS = [
    ["executive", /\b(chief\s+\w+\s+officer|cto|ceo|cfo|coo|president)\b/i],
    ["director", /\b(director|vp|vice\s+president|head\s+of)\b/i],
    ["internship", /\b(intern(ship)?|trainee|new\s+grad|graduate\s+program|pasant[ií]a)\b/i],
    ["entry", /\b(entry[\s-]?level|junior|jr\.?|joven\s+profesional)\b/i],
    ["associate", /\bassociate\b/i],
    ["staff", /\b(staff|principal|lead|expert|specialist)\b/i],
    ["senior", /\b(senior|sr\.?|semi[\s-]?senior|mid[\s-]?senior)\b/i],
    ["mid", /\bmid[\s-]?level\b/i],
  ];

  const TECHNOLOGIES = {
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud platform", "google cloud"],
    "Python": ["python"],
    "JavaScript": ["javascript", "ecmascript"],
    "TypeScript": ["typescript"],
    "Java": ["java"],
    "C#": ["c#", "c sharp", "c-sharp"],
    ".NET": [".net", "dotnet", "dot net"],
    "Go": ["golang", "go language"],
    "Ruby": ["ruby", "ruby on rails"],
    "PHP": ["php"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Scala": ["scala"],
    "Rust": ["rust"],
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular", "angularjs"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Next.js": ["next.js", "nextjs"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Express": ["express.js", "expressjs"],
    "Django": ["django"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Spring": ["spring boot", "spring framework"],
    "Laravel": ["laravel"],
    "Rails": ["rails", "ruby on rails"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo db"],
    "DynamoDB": ["dynamodb", "dynamo db"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "Kafka": ["kafka", "apache kafka"],
    "RabbitMQ": ["rabbitmq", "rabbit mq"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "Linux": ["linux"],
    "Git": ["git", "gitlab", "github"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous delivery"],
    "GraphQL": ["graphql"],
    "REST": ["rest api", "restful api"],
    "Microservices": ["microservices", "micro-services"],
    "Machine Learning": ["machine learning", "ml models"],
    "Data Engineering": ["data engineering", "data pipelines"],
  };

  const REQUIRED_MARKER = /\b(required|requirements?|must[\s-]?have|mandatory|essential|minimum\s+(?:qualifications?|requirements?)|obligatory|requisit[oa]s?|excluyente)\b/i;
  const REQUIRED_HEADING = /^(requirements?|qualifications?|what\s+you(?:'|’)ll\s+need|what\s+you\s+need|must\s+haves?|skills\s+(?:and|&)?\s+experience|requisitos?|calificaciones?)\s*:?$/i;
  const OPTIONAL_HEADING = /^(nice\s+to\s+haves?|preferred|bonus|desirable|plus|deseable|valorado)\s*:?$/i;
  const YEAR_RE = /\b(?:at\s+least|minimum\s+(?:of|:)?|more\s+than|over|m[aá]s\s+de|m[ií]nimo\s+de)?\s*(\d{1,2})\s*\+?\s*(?:-|–|to|a)?\s*(?:\d{1,2}\s*)?(?:years?|a[nñ]os?)\s*(?:of\s+)?(?:hands-on\s+|commercial\s+|professional\s+|relevant\s+|practical\s+)?(?:experience|exp\.?|de\s+experiencia)?/gi;
  const EMPLOYEE_RE = /(\d[\d,.]{0,8})\s*(?:\+|[-–]|to|a)\s*(\d[\d,.]{0,8})?\s*employees\b|(\d[\d,.]{0,8})\+?\s*employees\b/gi;

  function normalizeText(value) {
    return String(value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }

  function normalizeTechnology(value) {
    const compact = normalizeText(value).toLowerCase();
    for (const [canonical, aliases] of Object.entries(TECHNOLOGIES)) {
      if (aliases.some((alias) => compact === alias.toLowerCase())) return canonical;
    }
    return normalizeText(value);
  }

  function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function hasTechnology(text, technology) {
    const canonical = normalizeTechnology(technology);
    const aliases = TECHNOLOGIES[canonical] || [canonical];
    return aliases.some((alias) => {
      const escaped = escapeRegex(alias).replace(/\\ /g, "\\s+");
      // A dot may be part of a technology name (for example Node.js), but a
      // sentence-ending dot must still count as a valid boundary for AWS.
      return new RegExp(`(^|[^a-z0-9+#.])${escaped}(?=$|[^a-z0-9+#.]|\\.(?=\\s|$))`, "i").test(text);
    });
  }

  function extractTechnologies(text) {
    const source = normalizeText(text);
    return Object.keys(TECHNOLOGIES).filter((technology) => hasTechnology(source, technology));
  }

  function splitLines(text) {
    return String(text || "")
      .replace(/\r/g, "")
      .split(/\n+|(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜ])/)
      .map((line) => normalizeText(line.replace(/^[•*·\-–]+\s*/, "")))
      .filter(Boolean);
  }

  function extractRequiredTechnologies(description) {
    const required = new Set();
    let inRequiredSection = false;
    for (const line of splitLines(description)) {
      if (OPTIONAL_HEADING.test(line)) {
        inRequiredSection = false;
        continue;
      }
      if (REQUIRED_HEADING.test(line)) {
        inRequiredSection = true;
        continue;
      }
      const isRequired = inRequiredSection || REQUIRED_MARKER.test(line);
      if (!isRequired) continue;
      extractTechnologies(line).forEach((technology) => required.add(technology));
    }
    return [...required];
  }

  function extractMinimumYears(description) {
    const matches = [];
    const text = String(description || "");
    let match;
    YEAR_RE.lastIndex = 0;
    while ((match = YEAR_RE.exec(text))) {
      const years = Number(match[1]);
      if (Number.isInteger(years) && years > 0 && years <= 40) matches.push(years);
    }
    return matches.length ? Math.min(...matches) : null;
  }

  function extractSeniority(title, description) {
    const source = `${title || ""} ${description || ""}`;
    for (const [level, pattern] of SENIORITY_PATTERNS) {
      if (pattern.test(source)) return level;
    }
    const years = extractMinimumYears(description);
    return years !== null && years > 5 ? "mid" : "entry";
  }

  function parseEmployeeNumber(value) {
    const numeric = String(value || "").replace(/[^\d]/g, "");
    const parsed = Number(numeric);
    return Number.isFinite(parsed) && parsed > 0 && parsed <= 2_000_000 ? parsed : null;
  }

  function extractCompanySize(text) {
    const source = String(text || "");
    let match;
    let highest = null;
    EMPLOYEE_RE.lastIndex = 0;
    while ((match = EMPLOYEE_RE.exec(source))) {
      const candidates = [match[1], match[2], match[3]].map(parseEmployeeNumber).filter(Boolean);
      if (candidates.length) highest = Math.max(highest || 0, ...candidates);
    }
    if (!highest) return "unknown";
    if (highest <= 200) return "startup";
    if (highest <= 5000) return "midsize";
    return "enterprise";
  }

  function extractNativeFilters(url) {
    const parsed = new URL(url || "https://www.linkedin.com/jobs/search/");
    const keywords = parsed.searchParams.get("keywords") || "";
    const location = parsed.searchParams.get("location") || "";
    const experience = parsed.searchParams.get("f_E") || "";
    const workType = parsed.searchParams.get("f_WT") || "";
    return {
      keywords,
      location,
      experience: experience ? experience.split(",") : [],
      workType: workType ? workType.split(",") : [],
    };
  }

  function defaultFilters() {
    return {
      maxYears: null,
      allowedSeniorities: [],
      includeTechnologies: [],
      excludeTechnologies: [],
      companySizes: [],
    };
  }

  function technologiesMatch(technologies, chips) {
    return chips.some((chip) => {
      const normalized = normalizeTechnology(chip);
      return technologies.some((technology) => normalizeTechnology(technology) === normalized)
        || hasTechnology(technologies.join(" "), normalized);
    });
  }

  function evaluate(job, filters) {
    const activeFilters = { ...defaultFilters(), ...(filters || {}) };
    const reasons = [];
    const unknown = [];
    const requiredTechnologies = Array.isArray(job.requiredTechnologies) ? job.requiredTechnologies : [];

    if (activeFilters.maxYears) {
      if (job.minYears === null || job.minYears === undefined) unknown.push("años");
      else if (job.minYears > activeFilters.maxYears) reasons.push(`pide ${job.minYears}+ años`);
    }
    if (activeFilters.allowedSeniorities.length) {
      if (!job.seniority) unknown.push("seniority");
      else if (!activeFilters.allowedSeniorities.includes(job.seniority)) reasons.push(`nivel ${job.seniority}`);
    }
    if (activeFilters.includeTechnologies.length) {
      if (!requiredTechnologies.length) unknown.push("tecnologías");
      else if (!technologiesMatch(requiredTechnologies, activeFilters.includeTechnologies)) reasons.push("sin tecnologías incluidas");
    }
    if (activeFilters.excludeTechnologies.length && technologiesMatch(requiredTechnologies, activeFilters.excludeTechnologies)) {
      reasons.push("tecnología excluida");
    }
    if (activeFilters.companySizes.length) {
      if (!job.companySize || job.companySize === "unknown") unknown.push("tamaño de empresa");
      else if (!activeFilters.companySizes.includes(job.companySize)) reasons.push(`empresa ${job.companySize}`);
    }

    return {
      visible: reasons.length === 0,
      state: reasons.length ? "filtered" : unknown.length ? "unknown" : "match",
      reasons,
      unknown,
    };
  }

  const api = {
    SENIORITY_LEVELS,
    defaultFilters,
    normalizeTechnology,
    extractTechnologies,
    extractRequiredTechnologies,
    extractMinimumYears,
    extractSeniority,
    extractCompanySize,
    extractNativeFilters,
    evaluate,
  };

  global.JobFilterRules = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
