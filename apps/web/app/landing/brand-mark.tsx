// The crosspod mark (public/brand/crosspod-icon.jpg) as vector paths, so it
// paints with the first byte of HTML and can take any color. The wide stroke
// rounds the corners the way the logo does.
export default function BrandMark({
  className,
  size,
  color = "currentColor",
}: {
  className?: string;
  size?: number;
  color?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 1000 935"
      fill={color}
      stroke={color}
      strokeWidth={80}
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M500 45 L860 205 L500 362 L140 205 Z" />
      <path d="M40 333 L440 533 Q500 563 560 533 L960 333 L960 414 L560 610 Q500 640 440 610 L40 414 Z" />
      <path d="M40 582 L440 782 Q500 812 560 782 L960 582 L960 663 L560 859 Q500 889 440 859 L40 663 Z" />
    </svg>
  );
}
