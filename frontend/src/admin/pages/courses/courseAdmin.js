/** The admin list endpoints return {page, page_size, total}; Pagination wants totals. */
export function toPagination(meta) {
  if (!meta?.total) return null;
  const totalPages = Math.max(1, Math.ceil(meta.total / meta.page_size));
  return {
    page: meta.page,
    total: meta.total,
    total_pages: totalPages,
    has_prev: meta.page > 1,
    has_next: meta.page < totalPages,
  };
}

export const ASSESSMENT_KINDS = [
  { value: "quiz", label: "Quiz (scored automatically)" },
  { value: "reflection", label: "Written reflection (ungraded)" },
  { value: "self_assessment", label: "Self-assessment (ungraded ratings)" },
];

export const QUESTION_KINDS = {
  quiz: [
    { value: "single_choice", label: "Single choice" },
    { value: "multiple_select", label: "Multiple select" },
    { value: "true_false", label: "True / false" },
    { value: "short_text", label: "Written answer (not scored)" },
  ],
  reflection: [
    { value: "short_text", label: "Written answer" },
    { value: "rating", label: "Rating scale" },
  ],
  self_assessment: [
    { value: "rating", label: "Rating scale" },
    { value: "short_text", label: "Written answer" },
  ],
  // Question banks feed quizzes and practice exams.
  bank: [
    { value: "single_choice", label: "Single choice" },
    { value: "multiple_select", label: "Multiple select" },
    { value: "true_false", label: "True / false" },
    { value: "short_text", label: "Written answer (not scored)" },
    { value: "rating", label: "Rating scale (not scored)" },
  ],
};

export function newQuestion(kind) {
  if (kind === "single_choice" || kind === "multiple_select")
    return {
      kind,
      prompt: "",
      options: [
        { id: "a", text: "" },
        { id: "b", text: "" },
      ],
      correct: [],
      explanation: "",
      points: 1,
      required: true,
    };
  if (kind === "true_false")
    return { kind, prompt: "", correct: ["true"], explanation: "", points: 1, required: true };
  if (kind === "rating")
    return {
      kind,
      prompt: "",
      settings: { scale: 5, min_label: "", max_label: "" },
      required: true,
    };
  return { kind, prompt: "", settings: { max_length: 2000 }, required: true };
}
