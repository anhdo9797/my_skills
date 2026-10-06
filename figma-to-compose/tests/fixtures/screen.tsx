const imgIcon = "https://www.figma.com/api/mcp/asset/abc123.svg";
const imgChevron = "https://www.figma.com/api/mcp/asset/def456.svg";
const imgThumb = "https://www.figma.com/api/mcp/asset/thumb789.png";

type CardProps = { className?: string; variant?: "Spicy" | "Calm" };

function TopicCard({ className, variant = "Calm" }: CardProps) {
  const isSpicy = variant === "Spicy";
  return (
    <div className={className || `${isSpicy ? "bg-[#ffe9ea]" : "bg-[#ecfdf5]"} content-stretch flex flex-col gap-[4px] p-[12px] relative rounded-[16px]`} id={isSpicy ? "node-5_7804" : "node-5_7744"}>
      <p className="font-['Inter:Medium',sans-serif] font-medium leading-[20px] text-[#141414] text-[14px]" data-node-id="5:7750">
        {isSpicy ? "Spicy" : "Calm"}
      </p>
    </div>
  );
}

export default function Connect() {
  return (
    <div className="bg-white content-stretch flex flex-col gap-[16px] items-start px-[20px] py-[24px] relative size-full" data-name="Connect" data-node-id="5:8469">
      <div className="content-stretch flex gap-[12px] items-center relative shrink-0 w-full" data-name="row" data-node-id="5:8470">
        <div className="relative shrink-0 size-[24px]" data-name="icon" data-node-id="5:8471">
          <img alt="" className="block max-w-none size-full" src={imgIcon} />
        </div>
        <div className="flex flex-[1_0_0] flex-col font-['Inter:Semi_Bold',sans-serif] font-semibold justify-center leading-[0] min-h-px min-w-px not-italic relative text-[#141414] text-[18px] tracking-[-0.02em]" data-node-id="5:8472">
          <p className="leading-[24px]">Kết nối</p>
        </div>
        <div className="relative shrink-0 size-[16px]" data-name="chevron" data-node-id="5:8473">
          <img alt="" className="block max-w-none size-full" src={imgChevron} />
        </div>
      </div>
      <div className="font-['Inter:Regular'] font-normal text-[#8e9aa8] content-stretch flex flex-col items-start relative shrink-0 w-full" data-node-id="5:8480" data-name="info">
        <p className="leading-[0] relative shrink-0 text-[11px] whitespace-nowrap" data-node-id="5:8481">
          <span className="leading-[normal]">{`Kích thước: `}</span>
          <span className="leading-[normal] text-[#00dc82]">~3.6 MB</span>
        </p>
        <p className="leading-[1.5] relative shrink-0 text-[12px] uppercase" data-node-id="5:8482">
          Line one&apos;s
          <br aria-hidden="true" />
          line two
        </p>
      </div>
      <div className="bg-gradient-to-b from-[#fd75a7] to-[#ff9a8b] content-stretch flex items-center justify-center px-[24px] py-[14px] relative rounded-[999px] shadow-[0px_4px_12px_0px_rgba(253,117,167,0.35)] shrink-0" data-name="cta" data-node-id="5:8474">
        <p className="font-['Inter:Bold',sans-serif] font-bold leading-[20px] not-italic relative shrink-0 text-[14px] text-center text-nowrap text-white uppercase whitespace-pre" data-node-id="5:8475">Khám phá</p>
      </div>
      <div className="bg-[rgba(20,20,20,0.06)] border-[#e5e5e5] border-[1.5px] border-solid h-px opacity-80 shrink-0 w-full" data-name="divider" data-node-id="5:8476" />
      <div className="relative rounded-tl-[16px] rounded-bl-[16px] shrink-0 w-[3px] h-[40px] drop-shadow-[0px_4px_6px_rgba(0,219,130,0.35)]" data-node-id="5:8477" data-name="accent" style={{ backgroundImage: "linear-gradient(91.5deg, rgb(74, 222, 128) 25%, rgb(20, 184, 166) 75%)" }} />
      <div className="aspect-square overflow-clip relative rounded-[12px] shrink-0 w-full" data-node-id="5:8478" data-name="thumb">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <img alt="" className="absolute h-[208%] left-0 max-w-none top-[-54%] w-full object-cover" src={imgThumb} />
        </div>
      </div>
      <TopicCard className="bg-[#ffe9ea] content-stretch flex flex-col p-[12px] relative rounded-[16px] shrink-0 w-full" variant="Spicy" data-node-id="5:8490" data-name="Topic card" />
      <TopicCard className="bg-[#ecfdf5] content-stretch flex flex-col p-[12px] relative rounded-[16px] shrink-0 w-full" data-node-id="5:8491" data-name="Topic card" />
    </div>
  );
}
