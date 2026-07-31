"use client"

import React, { createContext, useContext, useState, useEffect } from "react"

export type Locale = "en" | "sk"

interface I18nContextType {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: string, variables?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

const translations: Record<Locale, Record<string, string>> = {
  en: {},
  sk: {}
}

export const I18nProvider: React.FC<{
  children: React.ReactNode
  enDict: Record<string, string>
  skDict: Record<string, string>
}> = ({ children, enDict, skDict }) => {
  translations.en = enDict
  translations.sk = skDict

  const [locale, setLocaleState] = useState<Locale>("en")

  useEffect(() => {
    const saved = localStorage.getItem("leadscope_locale") as Locale
    if (saved === "en" || saved === "sk") {
      setLocaleState(saved)
    }
  }, [])

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale)
    localStorage.setItem("leadscope_locale", newLocale)
  }

  const t = (key: string, variables?: Record<string, string | number>) => {
    const defaultValue = typeof variables?.defaultValue === "string" ? variables.defaultValue : undefined
    let str = translations[locale][key] || translations["en"][key] || defaultValue || key
    if (variables) {
      Object.keys(variables).forEach((k) => {
        if (k !== "defaultValue") {
          str = str.replace(new RegExp(`{{${k}}}`, "g"), String(variables[k]))
        }
      })
    }
    return str
  }

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export const useTranslation = () => {
  const context = useContext(I18nContext)
  if (context === undefined) {
    throw new Error("useTranslation must be used within an I18nProvider")
  }
  return context
}
