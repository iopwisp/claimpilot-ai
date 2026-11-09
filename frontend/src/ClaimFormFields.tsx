import { Claim } from "./api";
export function ClaimFormFields({ claim }: { claim?: Claim }) {
  return (
    <>
      <label>
        Claimant name
        <input
          name="claimant_name"
          required
          maxLength={160}
          defaultValue={claim?.claimant_name}
        />
      </label>
      <div className="grid2">
        <label>
          Policy number
          <input
            name="policy_number"
            required
            maxLength={80}
            defaultValue={claim?.policy_number}
          />
        </label>
        <label>
          Incident date
          <input
            name="incident_date"
            type="date"
            required
            defaultValue={claim?.incident_date}
          />
        </label>
        <label>
          Claim amount
          <input
            type="number"
            name="claim_amount"
            min="0"
            step=".01"
            required
            defaultValue={claim?.claim_amount}
          />
        </label>
        <label>
          Currency
          <input
            name="currency"
            defaultValue={claim?.currency || "USD"}
            pattern="[A-Z]{3}"
            required
          />
        </label>
      </div>
      <label>
        Incident description
        <textarea
          name="incident_description"
          maxLength={5000}
          required
          defaultValue={claim?.incident_description}
        />
      </label>
    </>
  );
}
