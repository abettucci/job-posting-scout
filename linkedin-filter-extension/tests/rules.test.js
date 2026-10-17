const test = require("node:test");
const assert = require("node:assert/strict");
const rules = require("../rules.js");

test("extracts seniority and the minimum requested years", () => {
  const description = "Minimum of 3 years of professional experience. Senior title ownership is expected.";
  assert.equal(rules.extractMinimumYears(description), 3);
  assert.equal(rules.extractSeniority("Senior Backend Engineer", description), "senior");
});

test("extracts only required technologies, excluding a nice-to-have section", () => {
  const description = `Requirements:\n- Python and AWS are required\n- Experience with PostgreSQL\nNice to have:\n- Kafka`;
  assert.deepEqual(rules.extractRequiredTechnologies(description), ["AWS", "Python", "PostgreSQL"]);
  assert.deepEqual(rules.extractTechnologies(description), ["AWS", "Python", "PostgreSQL", "Kafka"]);
});

test("recognizes an inline requirements heading from rendered LinkedIn text", () => {
  const description = "Requirements: 3+ years with Python and AWS. Nice to have: Kafka.";
  assert.deepEqual(rules.extractRequiredTechnologies(description), ["AWS", "Python"]);
});

test("uses employee ranges to create a company-size bucket", () => {
  assert.equal(rules.extractCompanySize("51-200 employees"), "startup");
  assert.equal(rules.extractCompanySize("1,001-5,000 employees"), "midsize");
  assert.equal(rules.extractCompanySize("10,001+ employees"), "enterprise");
  assert.equal(rules.extractCompanySize("No size data"), "unknown");
});

test("keeps unknown data visible and applies included/excluded technology filters", () => {
  const filters = {
    maxYears: 4,
    allowedSeniorities: ["entry", "mid"],
    includeTechnologies: ["Python", "AWS"],
    excludeTechnologies: ["SAP"],
    companySizes: ["startup", "midsize"],
  };
  const unknown = rules.evaluate({ minYears: null, seniority: "mid", requiredTechnologies: [], companySize: "unknown" }, filters);
  assert.equal(unknown.visible, true);
  assert.equal(unknown.state, "unknown");

  const matched = rules.evaluate({ minYears: 3, seniority: "mid", requiredTechnologies: ["Python"], companySize: "startup" }, filters);
  assert.equal(matched.visible, true);
  assert.equal(matched.state, "match");

  const excluded = rules.evaluate({ minYears: 3, seniority: "mid", requiredTechnologies: ["Python", "SAP"], companySize: "startup" }, filters);
  assert.equal(excluded.visible, false);
  assert.match(excluded.reasons.join(" "), /excluida/);
});
