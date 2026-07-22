import { describe, it, expect } from "vitest"
import { csvField } from "../../app/api/leads/export/route"

describe("csvField formula injection protection", () => {
  it("normal strings pass through unchanged", () => {
    expect(csvField("Acme Corp")).toBe('"Acme Corp"')
    expect(csvField("123 Main St")).toBe('"123 Main St"')
  })

  it("strings starting with = get prefixed with '", () => {
    expect(csvField("=1+1")).toBe("\"'=1+1\"")
    expect(csvField("=cmd|' /C calc'!A0")).toBe("\"'=cmd|' /C calc'!A0\"")
  })

  it("strings starting with +, -, @ get prefixed with '", () => {
    expect(csvField("+SUM(1,1)")).toBe("\"'+SUM(1,1)\"")
    expect(csvField("-1+2")).toBe("\"'-1+2\"")
    expect(csvField("@SUM(1,1)")).toBe("\"'@SUM(1,1)\"")
  })

  it("strings starting with \\t or \\r get prefixed with '", () => {
    expect(csvField("\tSUM(1,1)")).toBe("\"'\tSUM(1,1)\"")
    expect(csvField("\rSUM(1,1)")).toBe("\"'\rSUM(1,1)\"")
  })

  it("double quotes inside values are escaped as \"\"", () => {
    expect(csvField('Acme "The Best" Corp')).toBe('"Acme ""The Best"" Corp"')
    expect(csvField('="malicious"')).toBe("\"'=\"\"malicious\"\"\"")
  })

  it("null/undefined return empty string", () => {
    expect(csvField(null)).toBe("")
    expect(csvField(undefined)).toBe("")
  })
})
