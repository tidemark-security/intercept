import * as React from "react";
import { IconWrapper } from "@/utils/IconWrapper";

const MSTeamsIcon = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement>
>(function MSTeamsIcon(props, ref) {
  return (
    <IconWrapper ref={ref} {...props}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="1em"
        height="1em"
        viewBox="0 0 6.35 6.35"
        fill="none"
      >
        <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
          <g fill="none">
            <path
              d="m4.7625 5.8208h-2.6458s-1.3229 0.066181-1.3229-1.1727l4e-8 -1.2221s5.2e-6 -0.78012 0.79376-0.78012h1.5875s0.79375 0 0.79375 0.79375v1.5875s4e-7 0.79375 0.79375 0.79375z"
              strokeWidth=".52917"
              style={{ paintOrder: "markers fill stroke" }}
            />
            <g strokeWidth=".52917">
              <path
                d="m3.9688 3.175h1.1642s0.42334 0.038199 0.42334 0.52917l-1.17e-5 1.3229s0 0.79375-0.79375 0.79375h-0.52916"
                style={{ paintOrder: "markers fill stroke" }}
              />
              <ellipse
                cx="4.6302"
                cy="1.7198"
                rx=".39688"
                ry=".39688"
                style={{ paintOrder: "markers fill stroke" }}
              />
              <ellipse
                cx="2.3813"
                cy="1.0583"
                rx=".52917"
                ry=".52917"
                style={{ paintOrder: "markers fill stroke" }}
              />
            </g>
          </g>
          <path
            d="m2.3813 3.7042v1.0583"
            fill="#fff"
            strokeWidth=".52917"
            style={{ paintOrder: "markers fill stroke" }}
          />
          <path
            d="m1.8521 3.7042h1.0583"
            fill="#fff"
            strokeWidth=".52917"
            style={{ paintOrder: "markers fill stroke" }}
          />
        </g>
      </svg>
    </IconWrapper>
  );
});

export default MSTeamsIcon;
