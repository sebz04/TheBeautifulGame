// A monthly budget on the subscription with email alerts at 50% and 100% of it.
targetScope = 'subscription'

param amount int
param alertEmail string
param startDate string = '2026-10-01'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-matchmind'
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: { startDate: startDate }
    notifications: {
      half: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [alertEmail]
      }
      full: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [alertEmail]
      }
    }
  }
}
