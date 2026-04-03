import { NextRequest, NextResponse } from 'next/server'
import OpenAI from 'openai'

// OpenAI 클라이언트는 서버에서만 초기화 — API 키가 클라이언트에 노출되지 않음
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
})

const LANG_MAP: Record<string, string> = {
  ko: '한국어', en: '영어', ja: '일본어',
  zh: '중국어', de: '독일어', fr: '프랑스어', es: '스페인어',
}

export async function POST(req: NextRequest) {
  try {
    const { text, sourceLang, targetLang, contentType } = await req.json()

    if (!text?.trim()) {
      return NextResponse.json({ error: '번역할 텍스트가 없습니다.' }, { status: 400 })
    }

    const sourceLabel = LANG_MAP[sourceLang] ?? sourceLang
    const targetLabel = LANG_MAP[targetLang] ?? targetLang
    const domainHint = contentType ? ` 문서 유형은 ${contentType}입니다.` : ''

    // gpt-4o-mini: 비용 대비 성능이 우수하고 번역 품질이 충분함
    // temperature 0.3: 번역은 창의성보다 정확성이 중요하므로 낮게 설정
    const completion = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: `당신은 전문 번역가입니다.${domainHint} ${sourceLabel}를 ${targetLabel}로 번역하세요. 번역문만 출력하고 설명은 하지 마세요.`,
        },
        {
          role: 'user',
          content: text,
        },
      ],
      temperature: 0.3,
    })

    const translation = completion.choices[0]?.message?.content ?? ''
    return NextResponse.json({ translation })
  } catch (err) {
    console.error('Translation error:', err)
    return NextResponse.json({ error: '번역 중 오류가 발생했습니다.' }, { status: 500 })
  }
}
