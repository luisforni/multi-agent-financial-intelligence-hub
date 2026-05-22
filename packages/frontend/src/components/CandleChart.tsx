import { useEffect, useRef } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'
import type { Candle } from '../types'
import { computeRSI, computeMACD, computeBollingerBands, computeSMA } from '../lib/indicators'

interface Props {
  candles: Candle[]
  supportLevels?: number[]
  resistanceLevels?: number[]
  showRSI?: boolean
  showMACD?: boolean
}

const THEME = {
  bg: '#1e222d',
  bgDark: '#131722',
  grid: '#2a2e39',
  text: '#787b86',
  border: '#2a2e39',
  buy: '#26a69a',
  sell: '#ef5350',
  neutral: '#2962ff',
  hold: '#b2b5be',
}

export function CandleChart({
  candles,
  supportLevels = [],
  resistanceLevels = [],
  showRSI = true,
  showMACD = true,
}: Props) {
  const mainRef = useRef<HTMLDivElement>(null)
  const rsiRef = useRef<HTMLDivElement>(null)
  const macdRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!mainRef.current || candles.length < 2) return

    const closes = candles.map((c) => c.close)
    const times = candles.map((c) => c.time as string)

    const main = createChart(mainRef.current, {
      layout: { background: { type: ColorType.Solid, color: THEME.bg }, textColor: THEME.text },
      grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: THEME.border },
      timeScale: { borderColor: THEME.border, timeVisible: true, visible: !showRSI && !showMACD },
      width: mainRef.current.clientWidth,
      height: 280,
    })

    const cs = main.addCandlestickSeries({
      upColor: THEME.buy, downColor: THEME.sell,
      borderUpColor: THEME.buy, borderDownColor: THEME.sell,
      wickUpColor: THEME.buy, wickDownColor: THEME.sell,
    })
    cs.setData(candles.map((c) => ({
      time: c.time as Parameters<typeof cs.setData>[0][0]['time'],
      open: c.open, high: c.high, low: c.low, close: c.close,
    })))

    const vol = main.addHistogramSeries({
      color: THEME.neutral + '33',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })
    vol.setData(candles.map((c) => ({
      time: c.time as Parameters<typeof vol.setData>[0][0]['time'],
      value: c.volume,
      color: c.close >= c.open ? THEME.buy + '33' : THEME.sell + '33',
    })))

    const bb = computeBollingerBands(closes)
    const bbUpper = main.addLineSeries({ color: THEME.neutral + '55', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
    const bbMiddle = main.addLineSeries({ color: THEME.neutral + '88', lineWidth: 1, priceLineVisible: false })
    const bbLower = main.addLineSeries({ color: THEME.neutral + '55', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
    const toLine = (arr: (number | null)[]) =>
      arr.map((v, i) => v !== null ? ({ time: times[i] as Parameters<typeof bbUpper.setData>[0][0]['time'], value: v }) : null).filter(Boolean) as Parameters<typeof bbUpper.setData>[0]
    bbUpper.setData(toLine(bb.upper))
    bbMiddle.setData(toLine(bb.middle))
    bbLower.setData(toLine(bb.lower))

    const sma50 = computeSMA(closes, 50)
    const sma200 = computeSMA(closes, 200)
    const s50 = main.addLineSeries({ color: THEME.hold + '99', lineWidth: 1, priceLineVisible: false, title: 'SMA50' })
    const s200 = main.addLineSeries({ color: THEME.sell + '99', lineWidth: 1, priceLineVisible: false, title: 'SMA200' })
    s50.setData(toLine(sma50))
    s200.setData(toLine(sma200))

    for (const level of supportLevels.slice(0, 3)) {
      const line = main.addLineSeries({ color: THEME.buy, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false })
      line.setData(candles.map((c) => ({ time: c.time as Parameters<typeof line.setData>[0][0]['time'], value: level })))
    }
    for (const level of resistanceLevels.slice(0, 3)) {
      const line = main.addLineSeries({ color: THEME.sell, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false })
      line.setData(candles.map((c) => ({ time: c.time as Parameters<typeof line.setData>[0][0]['time'], value: level })))
    }

    main.timeScale().fitContent()

    let rsiChart: ReturnType<typeof createChart> | null = null
    if (showRSI && rsiRef.current) {
      rsiChart = createChart(rsiRef.current, {
        layout: { background: { type: ColorType.Solid, color: THEME.bgDark }, textColor: THEME.text },
        grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
        rightPriceScale: { borderColor: THEME.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
        timeScale: { borderColor: THEME.border, visible: !showMACD },
        width: rsiRef.current.clientWidth,
        height: 90,
      })

      const rsiValues = computeRSI(closes)
      const rsiLine = rsiChart.addLineSeries({ color: THEME.neutral, lineWidth: 1, priceLineVisible: false, title: 'RSI' })
      rsiLine.setData(toLine(rsiValues))

      const ob = rsiChart.addLineSeries({ color: THEME.sell + '55', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
      const os = rsiChart.addLineSeries({ color: THEME.buy + '55', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
      ob.setData(candles.map((c) => ({ time: c.time as Parameters<typeof ob.setData>[0][0]['time'], value: 70 })))
      os.setData(candles.map((c) => ({ time: c.time as Parameters<typeof os.setData>[0][0]['time'], value: 30 })))

      rsiChart.timeScale().fitContent()
    }

    let macdChart: ReturnType<typeof createChart> | null = null
    if (showMACD && macdRef.current) {
      macdChart = createChart(macdRef.current, {
        layout: { background: { type: ColorType.Solid, color: THEME.bgDark }, textColor: THEME.text },
        grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
        rightPriceScale: { borderColor: THEME.border },
        timeScale: { borderColor: THEME.border, timeVisible: true },
        width: macdRef.current.clientWidth,
        height: 90,
      })

      const { macd, signal, histogram } = computeMACD(closes)
      const macdLine = macdChart.addLineSeries({ color: THEME.neutral, lineWidth: 1, priceLineVisible: false, title: 'MACD' })
      const sigLine = macdChart.addLineSeries({ color: THEME.hold, lineWidth: 1, priceLineVisible: false, title: 'Signal' })
      const hist = macdChart.addHistogramSeries({ priceLineVisible: false, title: 'Hist' })

      macdLine.setData(toLine(macd))
      sigLine.setData(toLine(signal))
      hist.setData(
        histogram.map((v, i) => v !== null
          ? ({ time: times[i] as Parameters<typeof hist.setData>[0][0]['time'], value: v, color: v >= 0 ? THEME.buy + '88' : THEME.sell + '88' })
          : null
        ).filter(Boolean) as Parameters<typeof hist.setData>[0]
      )

      macdChart.timeScale().fitContent()
    }

    const charts = [rsiChart, macdChart].filter(Boolean) as ReturnType<typeof createChart>[]

    main.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) charts.forEach((c) => c.timeScale().setVisibleLogicalRange(range))
    })
    charts.forEach((c) => {
      c.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) {
          main.timeScale().setVisibleLogicalRange(range)
          charts.filter((x) => x !== c).forEach((x) => x.timeScale().setVisibleLogicalRange(range))
        }
      })
    })

    const observer = new ResizeObserver(() => {
      if (mainRef.current) main.applyOptions({ width: mainRef.current.clientWidth })
      if (rsiRef.current && rsiChart) rsiChart.applyOptions({ width: rsiRef.current.clientWidth })
      if (macdRef.current && macdChart) macdChart.applyOptions({ width: macdRef.current.clientWidth })
    })
    if (mainRef.current) observer.observe(mainRef.current)

    return () => {
      observer.disconnect()
      main.remove()
      rsiChart?.remove()
      macdChart?.remove()
    }
  }, [candles, supportLevels, resistanceLevels, showRSI, showMACD])

  return (
    <div className="w-full space-y-px">
      <div ref={mainRef} className="w-full overflow-hidden" />
      {showRSI && (
        <div className="relative">
          <span className="absolute top-1 left-2 text-[10px] text-muted z-10 pointer-events-none">RSI(14)</span>
          <div ref={rsiRef} className="w-full overflow-hidden" />
        </div>
      )}
      {showMACD && (
        <div className="relative">
          <span className="absolute top-1 left-2 text-[10px] text-muted z-10 pointer-events-none">MACD(12,26,9)</span>
          <div ref={macdRef} className="w-full overflow-hidden" />
        </div>
      )}
    </div>
  )
}
