export const siteConfig = {
  name: 'Adv. Aarav Sharma',
  brand: 'Adv. Aarav Sharma',
  legalName: 'Aarav Sharma & Associates',
  tagline: 'Clear counsel, when it matters.',
  url: process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000',
  description:
    'Book consultations online with an experienced advocate. Choose a service, pick a time, and confirm instantly.',
  nav: [
    { label: 'About', href: '/#about' },
    { label: 'Practice Areas', href: '/#practice-areas' },
    { label: 'Services', href: '/services' },
    { label: 'FAQ', href: '/#faq' },
    { label: 'Contact', href: '/#contact' },
  ],
  profile: {
    photo: '/lawyer.png',
    role: 'Advocate · High Court',
    name: 'Aarav Sharma',
    summary:
      'Counsels individuals and businesses across family, property, criminal, and commercial matters with a focus on plain-language advice and predictable outcomes.',
    highlights: [
      'Enrolled with the Bar Council of Delhi',
      '15+ years of courtroom and negotiation experience',
      'Adviser to early-stage founders and family offices',
      'Consultations in English and Hindi',
    ],
  },
  practiceAreas: [
    {
      title: 'Family & Matrimonial',
      description:
        'Divorce, mediation, custody, maintenance, and pre-nuptial considerations handled with discretion.',
    },
    {
      title: 'Property & Real Estate',
      description:
        'Title verification, sale deeds, landlord–tenant disputes, and builder-buyer issues.',
    },
    {
      title: 'Criminal Defense',
      description:
        'Bail, trial strategy, and representation through every stage of a criminal case.',
    },
    {
      title: 'Corporate & Commercial',
      description:
        'Contracts, due diligence, founder agreements, and commercial dispute resolution.',
    },
  ],
  faq: [
    {
      question: 'How do I book a consultation?',
      answer:
        'Choose a service, pick an available date and time, add your details, verify your phone, and pay. You get a confirmation instantly.',
    },
    {
      question: 'How will the consultation happen?',
      answer:
        'By phone or video, at the time you booked. Details and a calendar link are sent after confirmation.',
    },
    {
      question: 'Can I cancel or reschedule?',
      answer:
        'Yes — manage your bookings from the client portal. Cancellation and rescheduling rules depend on how far in advance you act.',
    },
    {
      question: 'What information do I need to provide?',
      answer:
        'Your name, a phone number for verification, and any context you want your advocate to have before the call.',
    },
  ],
  contact: {
    email: 'assist@example.in',
    phone: '+91 98765 43210',
    address: 'Chambers 12, District Court Complex, New Delhi',
    hours: 'Mon–Sat, 10:00 AM – 6:00 PM',
  },
} as const

export type SiteContact = (typeof siteConfig)['contact']
