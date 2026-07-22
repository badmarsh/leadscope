import { describe, it, expect } from "vitest"
import { csvField } from "@/app/api/leads/export/route"

describe("csvField (CSV Formula Injection Protection)", () => {
  it("passes normal strings through unchanged (wrapped in double-quotes)", () => {
    expect(csvField("Normal Company")).toBe('"Normal Company"')
    expect(csvField("12345")).toBe('"12345"')
  })

  it("prefixes strings starting with '=' with a single quote", () => {
    expect(csvField("=SUM(A1:A5)")).toBe('"' + "'=SUM(A1:A5)" + '"')
  })

  it("prefixes strings starting with '+', '-', '@', '\\t', '\\r' with a single quote", () => {
    expect(csvField("+12345")).toBe('"' + "'+12345" + '"')
    expect(csvField("-Negative")).toBe('"' + "'-Negative" + '"')
    expect(csvField("@username")).toBe('"' + "'@username" + '"')
    expect(csvField("\tTab")).toBe('"' + "'\tTab" + '"')
    expect(csvField("\rCarriage")).toBe('"' + "'\rCarriage" + '"')
  })

  it("escapes double-quotes inside values as two double-quotes", () => {
    expect(csvField('Company "Name"')).toBe('"Company ""Name"""')
    expect(csvField('="Formula"')).toBe('"\'' + '=""Formula"""')
  })

  it("returns an empty string for null and undefined", () => {
    expect(csvField(null)).toBe("")
    expect(csvField(undefined)).toBe("")
  })
})
