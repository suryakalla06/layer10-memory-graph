import pandas as pd

# Load dataset
df = pd.read_csv("data/emails.csv")

print("Total emails in dataset:", len(df))

# Take first 1000 emails
subset = df.head(1000)

print("Emails we will process:", len(subset))

# Show first email
print("\nExample email:\n")
print(subset.iloc[0]["message"])

# Save subset for faster future runs
subset.to_csv("data/emails_subset_1000.csv", index=False)

print("\nSaved subset to data/emails_subset_1000.csv")