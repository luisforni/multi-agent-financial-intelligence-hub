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
  bg: '#1a1d27',
  bgDark: '#0f1117',
  grid: '#2a2d3a',
  text: '#9ca3af',
  border: '#2a2d3a',
  buy: '#22c55e',
  sell: '#ef4444',
  neutral: '#6366f1',
  hold: '#f59e0b',
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

    // ── Main chart ──────────────────────────────────────────────────────────
    const main = createChart(mainRef.current, {
      layout: { background: { type: ColorType.Solid, color: THEME.bg }, textColor: THEME.text },
      grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: THEME.border },
      timeScale: { borderColor: THEME.border, timeVisible: true, visible: !showRSI && !showMACD },
      width: mainRef.current.clientWidth,
      height: 300,
    })

    // Candlesticks
    const cs = main.addCandlestickSeries({
      upColor: THEME.buy, downColor: THEME.sell,
      borderUpColor: THEME.buy, borderDownColor: THEME.sell,
      wickUpColor: THEME.buy, wickDownColor: THEME.sell,
    })
    cs.setData(candles.map((c) => ({
      time: c.time as Parameters<typeof cs.setData>[0][0]['time'],
      open: c.open, high: c.high, low: c.low, close: c.close,
    })))

    // Volume histogram (left scale)
    const vol = main.addHistogramSeries({
      color: '#6366f133',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })
    vol.setData(candles.map((c) => ({
      time: c.time as Parameters<typeof vol.setData>[0][0]['time'],
      value: c.volume,
      color: c.close >= c.open ? '#22c55e33' : '#ef444433',
    })))

    // Bollinger Bands
    const bb = computeBollingerBands(closes)
    const bbUpper = main.addLineSeries({ color: '#6366f155', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
    const bbMiddle = main.addLineSeries({ color: '#6366f188', lineWidth: 1, priceLineVisible: false })
    const bbLower = main.addLineSeries({ color: '#6366f155', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
    const toLine = (arr: (number | null)[]) =>
      arr.map((v, i) => v !== null ? ({ time: times[i] as Parameters<typeof bbUpper.setData>[0][0]['time'], value: v }) : null).filter(Boolean) as Parameters<typeof bbUpper.setData>[0]
    bbUpper.setData(toLine(bb.upper))
    bbMiddle.setData(toLine(bb.middle))
    bbLower.setData(toLine(bb.lower))

    // SMA 50 & 200
    const sma50 = computeSMA(closes, 50)
    const sma200 = computeSMA(closes, 200)
    const s50 = main.addLineSeries({ color: '#f59e0b99', lineWidth: 1, priceLineVisible: false, title: 'SMA50' })
    const s200 = main.addLineSeries({ color: '#ef444499', lineWidth: 1, priceLineVisible: false, title: 'SMA200' })
    s50.setData(toLine(sma50))
    s200.setData(toLine(sma200))

    // Support / Resistance
    for (const level of supportLevels.slice(0, 3)) {
      const line = main.addLineSeries({ color: THEME.buy, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false })
      line.setData(candles.map((c) => ({ time: c.time as Parameters<typeof line.setData>[0][0]['time'], value: level })))
    }
    for (const level of resistanceLevels.slice(0, 3)) {
      const line = main.addLineSeries({ color: THEME.sell, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false })
      line.setData(candles.map((c) => ({ time: c.time as Parameters<typeof line.setData>[0][0]['time'], value: level })))
    }

    main.timeScale().fitContent()

    // ── RSI chart ───────────────────────────────────────────────────────────
    let rsiChart: ReturnType<typeof createChart> | null = null
    if (showRSI && rsiRef.current) {
      rsiChart = createChart(rsiRef.current, {
        layout: { background: { type: ColorType.Solid, color: THEME.bgDark }, textColor: THEME.text },
        grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
        rightPriceScale: { borderColor: THEME.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
        timeScale: { borderColor: THEME.border, visible: !showMACD },
        width: rsiRef.current.clientWidth,
        height: 100,
      })

      const rsiValues = computeRSI(closes)
      const rsiLine = rsiChart.addLineSeries({ color: THEME.neutral, lineWidth: 1, priceLineVisible: false, title: 'RSI' })
      rsiLine.setData(toLine(rsiValues))

      // Overbought / Oversold reference lines
      const ob = rsiChart.addLineSeries({ color: '#ef444455', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
      const os = rsiChart.addLineSeries({ color: '#22c55e55', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false })
      ob.setData(candles.map((c) => ({ time: c.time as Parameters<typeof ob.setData>[0][0]['time'], value: 70 })))
      os.setData(candles.map((c) => ({ time: c.time as Parameters<typeof os.setData>[0][0]['time'], value: 30 })))

      rsiChart.timeScale().fitContent()
    }

    // ── MACD chart ──────────────────────────────────────────────────────────
    let macdChart: ReturnType<typeof createChart> | null = null
    if (showMACD && macdRef.current) {
      macdChart = createChart(macdRef.current, {
        layout: { background: { type: ColorType.Solid, color: THEME.bgDark }, textColor: THEME.text },
        grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
        rightPriceScale: { borderColor: THEME.border },
        timeScale: { borderColor: THEME.border, timeVisible: true },
        width: macdRef.current.clientWidth,
        height: 100,
      })

      const { macd, signal, histogram } = computeMACD(closes)
      const macdLine = macdChart.addLineSeries({ color: THEME.neutral, lineWidth: 1, priceLineVisible: false, title: 'MACD' })
      const sigLine = macdChart.addLineSeries({ color: THEME.hold, lineWidth: 1, priceLineVisible: false, title: 'Signal' })
      const hist = macdChart.addHistogramSeries({ priceLineVisible: false, title: 'Hist' })

      macdLine.setData(toLine(macd))
      sigLine.setData(toLine(signal))
      hist.setData(
        histogram.map((v, i) => v !== null
          ? ({ time: times[i] as Parameters<typeof hist.setData>[0][0]['time'], value: v, color: v >= 0 ? '#22c55e88' : '#ef444488' })
          : null
        ).filter(Boolean) as Parameters<typeof hist.setData>[0]
      )

      macdChart.timeScale().fitContent()
    }

    // ── Sync crosshair & time range ─────────────────────────────────────────
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

    // ── Resize observer ─────────────────────────────────────────────────────
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
    <div className="w-full space-y-0.5">
      <div ref={mainRef} className="w-full rounded-t-lg overflow-hidden" />
      {showRSI && (
        <div className="relative">
          <span className="absolute top-1 left-2 text-[10px] text-gray-500 z-10 pointer-events-none">RSI(14)</span>
          <div ref={rsiRef} className="w-full overflow-hidden" />
        </div>
      )}
      {showMACD && (
        <div className="relative">
          <span className="absolute top-1 left-2 text-[10px] text-gray-500 z-10 pointer-events-none">MACD(12,26,9)</span>
          <div ref={macdRef} className="w-full rounded-b-lg overflow-hidden" />
        </div>
      )}
    </div>
  )
}
