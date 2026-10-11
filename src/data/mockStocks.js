export const mockStocks = [
  { ticker: 'AAPL', name: 'Apple' },
  { ticker: 'MSFT', name: 'Microsoft' },
  { ticker: 'NVDA', name: 'NVIDIA' },
  { ticker: 'GOOG', name: 'Alphabet' },
  { ticker: 'AMZN', name: 'Amazon' },
  { ticker: 'TSLA', name: 'Tesla' },
  { ticker: 'ORCL', name: 'Oracle' },
  { ticker: 'JPM', name: 'JPMorgan Chase' },
  { ticker: 'KO', name: 'Coca-Cola' },
  { ticker: 'O', name: 'Realty Income' },
]

// Fictional presentation data. These are not calculated or live valuations.
export const demoValuation = {
  company: 'Microsoft Corporation',
  ticker: 'MSFT',
  exchange: 'NASDAQ',
  marketPrice: 420,
  fairValue: 485,
  upside: 15.5,
  marginOfSafety: 13.4,
  models: [
    {
      name: 'Discounted Cash Flow',
      shortName: 'DCF',
      value: 512,
      weight: '40%',
    },
    {
      name: 'Forward P/E',
      shortName: 'Forward P/E',
      value: 480,
      weight: '30%',
    },
    { name: 'EV/EBITDA', shortName: 'EV/EBITDA', value: 462, weight: '20%' },
    { name: 'EV/Revenue', shortName: 'EV/Revenue', value: 438, weight: '10%' },
  ],
  scenarios: [
    { name: 'Bear', value: 365, color: '#737373', change: '−13.1%' },
    { name: 'Base', value: 485, color: '#2563EB', change: '+15.5%' },
    { name: 'Bull', value: 580, color: '#171717', change: '+38.1%' },
  ],
}
