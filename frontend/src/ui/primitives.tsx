// src/ui/primitives.tsx
import type {
    ButtonHTMLAttributes,
    HTMLAttributes,
    ReactNode,
    SelectHTMLAttributes,
} from "react";

import { ui } from "./tokens";

type ButtonVariant = keyof typeof ui.button;
type SelectVariant = "default" | "compact" | "training";
type FieldLayout = "row" | "stack";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
    variant?: SelectVariant;
}

interface FieldProps {
    label?: ReactNode;
    layout?: FieldLayout;
    labelClassName?: string;
    className?: string;
    children: ReactNode;
}

type EmptyStateProps = HTMLAttributes<HTMLDivElement>;

const mergeClasses = (...parts: Array<string | undefined>) =>
    parts.filter(Boolean).join(" ");

export function Button({ variant, className, ...props }: ButtonProps) {
    const variantClass = variant ? ui.button[variant] : undefined;
    return (
        <button
            {...props}
            className={mergeClasses(variantClass, className)}
        />
    );
}

export function Select({ variant = "default", className, ...props }: SelectProps) {
    const variantClass =
        variant === "compact"
            ? ui.selectCompact
            : variant === "training"
            ? ui.trainingInput
            : ui.select;
    return (
        <select
            {...props}
            className={mergeClasses(variantClass, className)}
        />
    );
}

export function Field({
    label,
    layout = "stack",
    labelClassName,
    className,
    children,
}: FieldProps) {
    const baseClass =
        layout === "row" ? "flex items-center gap-2" : "flex flex-col gap-1";
    const resolvedLabelClass = labelClassName ?? ui.labelSmall;

    return (
        <div className={mergeClasses(baseClass, className)}>
            {label ? <span className={resolvedLabelClass}>{label}</span> : null}
            {children}
        </div>
    );
}

export function EmptyState({ className, ...props }: EmptyStateProps) {
    return (
        <div
            {...props}
            className={mergeClasses(ui.emptyBox, className)}
        />
    );
}
