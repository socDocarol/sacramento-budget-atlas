targetScope = 'subscription'

@description('Advisory monthly budget name.')
param budgetName string = 'budget-sac-budget-atlas-demo'

@description('Monthly budget amount in the subscription billing currency.')
@minValue(1)
param amount int = 15

@description('Email address that receives advisory budget notifications.')
param contactEmail string = 'docarol@cityofsacramento.org'

@description('Start of the first monthly budget period.')
param budgetStartDate string = '2026-08-01'

@description('End of the time-bounded experiment budget.')
param budgetEndDate string = '2026-10-01'

resource advisoryBudget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: budgetName
  properties: {
    amount: amount
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
      endDate: budgetEndDate
    }
    notifications: {
      Actual_GreaterThan_50_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [
          contactEmail
        ]
      }
      Actual_GreaterThan_80_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          contactEmail
        ]
      }
      Actual_GreaterThan_100_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [
          contactEmail
        ]
      }
    }
  }
}

output budgetName string = advisoryBudget.name
