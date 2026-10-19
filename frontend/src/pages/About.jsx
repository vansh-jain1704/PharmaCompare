import { FileUp, Info, ScanLine, ShieldCheck, Wallet } from "lucide-react";
import Page from "../components/Page";
import DataSources from "../components/DataSources";
import { DEMO_DISCLAIMER } from "../utils/disclaimers";

const STEPS = [
  { icon: FileUp, title: "Upload", text: "Add a photo or PDF of your prescription.", tone: "purple" },
  { icon: ScanLine, title: "Read and match", text: "We read the text and match each line to a medicine, with a confidence score.", tone: "teal" },
  { icon: ShieldCheck, title: "Check safety", text: "Interactions and your allergies are checked, and gaps are stated plainly.", tone: "orange" },
  { icon: Wallet, title: "Compare prices", text: "See cheaper same-ingredient options and what you could save.", tone: "lavender" },
];

const LIMITATIONS = [
  ["Handwriting", "very messy handwritten prescriptions may not be read correctly, even with Google Cloud Vision."],
  ["Dataset gaps", "some medicines (for example Zincovit) are missing from our dataset."],
  ["Match edge cases", "short brand names and combination drugs can sometimes be matched incorrectly; we show a confirmation step when unsure."],
  ["Safety coverage", "not all drug pairs are covered in the interaction database; some results will show \"data not available\"."],
  ["Prices", "the reference price comes from a community dataset snapshot, not a live pharmacy price. Pharmacy prices are shown only when a pharmacy has reported them, and are labelled with their age."],
  ["Availability", "stock is shown only when a pharmacy has reported it. There is no live stock source built in, so for most medicines no stock status can be shown."],
];

export default function About() {
  return (
    <Page
      width="narrow"
      crumbs={[{ label: "Home", to: "/" }, { label: "About" }]}
      eyebrow="About"
      title="About PharmaCompare"
    >
      <section className="about-section rise">
        <h2>What this app does</h2>
        <p>
          PharmaCompare turns a prescription photo into a clear medicine report: what each medicine is, whether
          anything needs a second look, and where you could pay less. It helps you understand a prescription. It
          never replaces your doctor or pharmacist.
        </p>
      </section>

      <section className="about-section rise d1">
        <h2>How it works</h2>
        <ol className="how-steps">
          {STEPS.map(({ icon: Icon, title, text, tone }, i) => (
            <li key={title} className={`tone-${tone}`}>
              <span className="how-icon"><Icon size={20} /></span>
              <div>
                <h3><span className="how-num">{i + 1}</span> {title}</h3>
                <p>{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="about-section rise d2">
        <h2>Data sources</h2>
        <p>Every figure comes from one of these. Sizes, dates and quality notes are counted from the data actually loaded.</p>
        <DataSources />
      </section>

      <section className="about-section rise d2">
        <h2>Limitations</h2>
        <ul className="bullets">
          {LIMITATIONS.map(([label, text]) => (
            <li key={label}><strong>{label}:</strong> {text}</li>
          ))}
        </ul>
        <div className="info-line">
          <Info size={14} aria-hidden="true" />
          <span><strong>Demo notice.</strong> {DEMO_DISCLAIMER} Pharmacy prices and stock appear only where a pharmacy has reported them, with the time of the report and the feed it came from. Where nothing is shown, no pharmacy has reported, and the only availability status taken from the dataset is its "discontinued" flag.</span>
        </div>
      </section>
    </Page>
  );
}
